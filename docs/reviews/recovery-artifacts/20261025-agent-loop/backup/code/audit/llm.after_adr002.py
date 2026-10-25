"""Thin model wrapper: provider routing, disk cache, usage ledger, offline fallback.

Only two places use a model: ambiguous request intent and one-time screenshot extraction.
Results are cached by prompt hash so re-runs are deterministic and cost nothing.

Providers (chosen by model id):
  gemini-*  Google Gemini Interactions API (POST /v1beta/interactions) over HTTPS with the
            standard library; key from GEMINI_API_KEY. Structured output via `response_format`
            (JSON schema), thinking via `generation_config.thinking_level`, `store: false`.
  claude-*  Anthropic Messages API through the optional `anthropic` SDK; key from ANTHROPIC_API_KEY.

Without a key (or SDK) for the requested model the wrapper reports that model unavailable and
callers fall back to deterministic behavior. Errors, refusals and incomplete answers return None.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .config import (API_KEY_ENV, GEMINI_API_KEY_ENV, GEMINI_ENDPOINT, MODEL_PRICES, USAGE_LEDGER)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def provider_for(model: str) -> str:
    if model.startswith("gemini-"):
        return "gemini"
    if model.startswith("claude-"):
        return "anthropic"
    return "unknown"


class LLM:
    def __init__(self, cache_path: Path, enabled: bool = True, trail=None, transport=None):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.trail = trail
        self.enabled = enabled
        self.client = None
        self.gemini_key = os.environ.get(GEMINI_API_KEY_ENV) if enabled else None
        self.transport = transport or _http_post_json      # injectable for offline tests
        self.usage = {"calls": 0, "cache_hits": 0, "by_model": {}}
        self._unavailable_logged: set = set()
        if enabled and os.environ.get(API_KEY_ENV):
            try:
                import anthropic                   # optional dependency
                self.client = anthropic.Anthropic()
            except ImportError:
                self.client = None

    @property
    def available(self) -> bool:
        """True if any provider is usable (kept for backward compatibility)."""
        return self.client is not None or bool(self.gemini_key)

    def available_for(self, model: str) -> bool:
        provider = provider_for(model)
        if provider == "gemini":
            return bool(self.gemini_key)
        if provider == "anthropic":
            return self.client is not None
        return False

    def json_call(self, model: str, prompt: str, schema: dict, image_png: bytes | None = None,
                  effort: str = "low", max_tokens: int = 4000, thinking_level: str | None = None) -> dict | None:
        key = hashlib.sha256(json.dumps([model, prompt, schema, hashlib.sha256(image_png or b"").hexdigest()],
                                        sort_keys=True).encode()).hexdigest()
        if key in self.cache:
            self.usage["cache_hits"] += 1
            return self.cache[key]["result"]
        if not self.available_for(model):
            if self.trail and model not in self._unavailable_logged:
                self._unavailable_logged.add(model)
                self.trail.write("llm_unavailable", model=model, provider=provider_for(model),
                                 reason="disabled" if not self.enabled else "no key or SDK")
            return None
        if provider_for(model) == "gemini":
            result, usage = self._gemini_call(model, prompt, schema, image_png, max_tokens, thinking_level, key)
        else:
            result, usage = self._anthropic_call(model, prompt, schema, image_png, effort, max_tokens, key)
        if usage:
            self._account(model, *usage)
        if result is None:
            return None
        self.cache[key] = {"model": model, "result": result}
        if self.trail:
            self.trail.write("llm_call", model=model, prompt_sha=key,
                             input_tokens=usage[0] if usage else None,
                             output_tokens=usage[1] if usage else None,
                             thought_tokens=usage[2] if usage else None)
        return result

    # ---- providers ---------------------------------------------------------------------------
    def _gemini_call(self, model, prompt, schema, image_png, max_tokens, thinking_level, key):
        parts = [{"type": "text", "text": prompt}]
        if image_png is not None:
            parts.append({"type": "image", "mime_type": "image/png", "resolution": "ultra_high",
                          "data": base64.standard_b64encode(image_png).decode()})
        body = {
            "model": model,
            "input": parts,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
            "generation_config": {"max_output_tokens": max_tokens},
            "store": False,
        }
        if thinking_level:
            body["generation_config"]["thinking_level"] = thinking_level
        try:
            response = self.transport(GEMINI_ENDPOINT, body, {"x-goog-api-key": self.gemini_key})
        except Exception as exc:                          # network / HTTP error: fail safe
            if self.trail:
                self.trail.write("llm_error", model=model, prompt_sha=key, error=type(exc).__name__)
            return None, None
        u = response.get("usage") or {}
        usage = (int(u.get("total_input_tokens") or 0), int(u.get("total_output_tokens") or 0),
                 int(u.get("total_thought_tokens") or 0))
        if response.get("status") != "completed":
            if self.trail:
                self.trail.write("llm_incomplete", model=model, prompt_sha=key, status=response.get("status"),
                                 errors=[e.get("code") for e in response.get("errors") or []])
            return None, usage
        text = next((c.get("text", "") for step in response.get("steps") or []
                     if step.get("type") == "model_output"
                     for c in step.get("content") or [] if c.get("type") == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            if self.trail:
                self.trail.write("llm_bad_json", model=model, prompt_sha=key)
            return None, usage

    def _anthropic_call(self, model, prompt, schema, image_png, effort, max_tokens, key):
        content = []
        if image_png is not None:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.standard_b64encode(image_png).decode()}})
        content.append({"type": "text", "text": prompt})
        try:
            response = self.client.beta.messages.create(
                model=model, max_tokens=max_tokens, betas=[FALLBACK_BETA], fallbacks="default",
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": content}],
            )
        except Exception as exc:                          # network / API error: fail safe
            if self.trail:
                self.trail.write("llm_error", model=model, prompt_sha=key, error=type(exc).__name__)
            return None, None
        usage = (response.usage.input_tokens, response.usage.output_tokens, 0)
        if response.stop_reason == "refusal":
            if self.trail:
                self.trail.write("llm_refusal", model=model, prompt_sha=key)
            return None, usage
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            if self.trail:
                self.trail.write("llm_bad_json", model=model, prompt_sha=key)
            return None, usage

    # ---- accounting ----------------------------------------------------------------------------
    def _account(self, model: str, input_tokens: int, output_tokens: int, thought_tokens: int = 0) -> None:
        self.usage["calls"] += 1
        m = self.usage["by_model"].setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                      "thought_tokens": 0})
        m["calls"] += 1
        m["input_tokens"] += input_tokens
        m["output_tokens"] += output_tokens
        m["thought_tokens"] = m.get("thought_tokens", 0) + thought_tokens

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True, ensure_ascii=False),
                                   encoding="utf-8")

    def record_usage(self, label: str, requests: int) -> dict:
        """Append this run's usage (with cost estimate) to the ledger used by usage_report.md.

        Thought tokens are billed at the output rate; they are added to output cost here in case the
        provider reports them separately from output tokens (conservative: never under-estimates).
        """
        total_cost = 0.0
        for model, m in self.usage["by_model"].items():
            pin, pout = MODEL_PRICES.get(model, (0.0, 0.0))
            billed_out = m["output_tokens"] + m.get("thought_tokens", 0)
            m["cost_usd"] = round(m["input_tokens"] / 1e6 * pin + billed_out / 1e6 * pout, 6)
            total_cost += m["cost_usd"]
        entry = {"label": label, "requests": requests, **self.usage, "total_cost_usd": round(total_cost, 6)}
        ledger = json.loads(USAGE_LEDGER.read_text(encoding="utf-8")) if USAGE_LEDGER.exists() else {}
        ledger[label] = entry
        USAGE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        USAGE_LEDGER.write_text(json.dumps(ledger, indent=1, sort_keys=True), encoding="utf-8")
        return entry


def _http_post_json(url: str, body: dict, headers: dict, timeout: float = 120.0) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:          # surface status without echoing request headers
        raise RuntimeError(f"HTTP {exc.code}") from None

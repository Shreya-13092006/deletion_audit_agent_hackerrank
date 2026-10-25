"""Planners: choose the next tool from the case's open gaps.

RulePlanner (default): deterministic priority order over gap kinds (state.GAP_ORDER); one call
closes every open gap of the chosen kind. GeminiPlanner (opt-in): asks a model which allowed tool
to run next, from a PII-free summary that uses opaque resource handles. Its answer is validated
(gate G7); anything invalid, unavailable or over budget falls back to the RulePlanner choice.
The model therefore influences only the order and batching of investigation - never identities,
states, citations or the final steps.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import AGENT_MAX_MODEL_CALLS_PER_CASE, AGENT_MAX_MODEL_CALLS_PER_RUN, PLANNER_MODEL, PLANNER_THINKING
from ..guardrails import scrub_pii
from .tools import tool_for_gap


@dataclass
class Choice:
    tool: str
    targets: list
    planner: str
    reason: str
    stop: bool = False


class RulePlanner:
    name = "rule"

    def __init__(self, registry: dict):
        self.registry = registry
        self.by_gap = tool_for_gap(registry)

    def next(self, state) -> Choice:
        kinds = state.open_kinds()
        if not kinds:
            return Choice("", [], self.name, "no open gaps", stop=True)
        kind = kinds[0]
        return Choice(self.by_gap[kind], state.targets(kind), self.name, f"highest-priority open gap {kind}")


PROMPT = """You are the planner of a data-deletion audit agent. Deterministic tools do all evidence
reading and decide every fact; you only choose which investigation to run next.

Open investigation gaps (kind -> resource handles; "" means case-level):
{gaps}

Tools you may call now (each closes the gaps of its kind; targets must be handles of that kind,
an empty list means all of them):
{tools}

Already run: {done}
Remaining budget: {budget} tool calls.

Pick the single most useful next tool. Prefer investigations that can uncover new records or
risks (links, sync paths, restore paths) before confirmations. Set stop=true only if no open gap
can be investigated."""


class GeminiPlanner:
    name = "gemini"

    def __init__(self, registry: dict, llm, trail=None, model: str = PLANNER_MODEL,
                 thinking: str = PLANNER_THINKING, per_case: int = AGENT_MAX_MODEL_CALLS_PER_CASE,
                 per_run: int = AGENT_MAX_MODEL_CALLS_PER_RUN):
        self.rule = RulePlanner(registry)
        self.registry = registry
        self.llm = llm
        self.trail = trail
        self.model, self.thinking = model, thinking
        self.per_case, self.per_run = per_case, per_run
        self.run_calls = 0
        self.rejections = 0

    def _fallback(self, state, why: str) -> Choice:
        c = self.rule.next(state)
        c.planner, c.reason = "rule_fallback", f"{why}; {c.reason}"
        return c

    def next(self, state, remaining_tools: int = 0) -> Choice:
        kinds = state.open_kinds()
        if not kinds:
            return Choice("", [], self.name, "no open gaps", stop=True)
        if self.llm is None or (not self.llm.available_for(self.model) and not self.llm.cache):
            return self._fallback(state, "planner model unavailable")
        if state.model_calls >= self.per_case or self.run_calls >= self.per_run:
            return self._fallback(state, "planner model budget exhausted")
        # Opaque handles only: no resource ids, emails, hashes or names leave the process.
        handle_kind = {}
        gaps_lines = []
        for kind in kinds:
            hs = [state.handles[t] for t in state.targets(kind) if t]
            for h in hs:
                handle_kind[h] = kind
            listed = ", ".join(hs) if hs else '""'
            gaps_lines.append(f"- {kind}: {listed}")
        allowed = {self.rule.by_gap[k]: k for k in kinds}
        tools_lines = [f"- {name}: {self.registry[name].description}" for name in sorted(allowed)]
        done = sorted({t.tool for t in state.tool_calls}) or ["none"]
        prompt = scrub_pii(PROMPT.format(gaps="\n".join(gaps_lines), tools="\n".join(tools_lines),
                                         done=", ".join(done), budget=remaining_tools))
        schema = {"type": "object",
                  "properties": {"tool": {"type": "string", "enum": sorted(allowed)},
                                 "targets": {"type": "array",
                                             "items": {"type": "string", "enum": sorted(handle_kind) or ["none"]}},
                                 "stop": {"type": "boolean"}, "reason": {"type": "string"}},
                  "required": ["tool", "targets", "stop", "reason"], "additionalProperties": False}
        calls_before = self.llm.usage["calls"]
        result = self.llm.json_call(self.model, prompt, schema, max_tokens=512, thinking_level=self.thinking)
        if self.llm.usage["calls"] > calls_before:
            state.model_calls += 1
            self.run_calls += 1
        if result is None:
            return self._fallback(state, "planner returned no valid answer")
        problem = self._validate(result, allowed, handle_kind)
        if problem:
            self.rejections += 1
            if self.trail:
                self.trail.write("planner_rejected", case_id=state.case.case_id, problem=problem,
                                 answer=json.dumps(result, sort_keys=True)[:300])
            return self._fallback(state, f"planner answer rejected ({problem})")
        tool = result["tool"]
        kind = allowed[tool]
        by_handle = {state.handles[t]: t for t in state.targets(kind) if t}
        chosen = [by_handle[h] for h in result["targets"] if h in by_handle]
        targets = sorted(chosen) if chosen else state.targets(kind)
        return Choice(tool, targets, self.name, str(result.get("reason", ""))[:200])

    @staticmethod
    def _validate(result: dict, allowed: dict, handle_kind: dict) -> str:
        if not isinstance(result, dict) or result.get("tool") not in allowed:
            return "tool not allowed for the open gaps"
        if result.get("stop"):
            return "stop requested while gaps can still be investigated"
        kind = allowed[result["tool"]]
        targets = result.get("targets") or []
        if isinstance(targets, list):
            targets = [h for h in targets if h != "none"]     # schema placeholder for "no handles"
            result["targets"] = targets
        if not isinstance(targets, list) or any(handle_kind.get(h) != kind for h in targets):
            return "targets are not open gaps of the chosen tool"
        return ""

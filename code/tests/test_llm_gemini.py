"""Gemini provider routing, request shape, response parsing and fail-safe paths (offline: the HTTP
transport is replaced by a fake, so no request ever leaves the machine)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts code/ on sys.path)

from audit import config
from audit.llm import LLM, provider_for

SCHEMA = {"type": "object", "properties": {"authorizes_deletion": {"type": "boolean"}},
          "required": ["authorizes_deletion"], "additionalProperties": False}


def ok_response(payload: dict, status="completed", usage=None):
    return {"status": status,
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}],
            "usage": usage or {"total_input_tokens": 120, "total_output_tokens": 9, "total_thought_tokens": 30}}


class FakeTransport:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, []

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        if self.exc:
            raise self.exc
        return self.response


def make_llm(transport, key="test-key-not-real"):
    tmp = Path(tempfile.mkdtemp()) / "cache.json"
    with mock.patch.dict(os.environ, {config.GEMINI_API_KEY_ENV: key, "AUDIT_LLM_RETRY_DELAYS": "0,0"}, clear=False):
        return LLM(tmp, enabled=True, transport=transport)


class RoutingTests(unittest.TestCase):
    def test_defaults_are_the_chosen_gemini_models(self):
        self.assertEqual(config.INTENT_MODEL, "gemini-3.5-flash-lite")
        self.assertEqual(config.VISION_MODEL, "gemini-3.8-flash")
        self.assertIn("gemini-3.5-flash-lite", config.MODEL_PRICES)
        self.assertIn("gemini-3.8-flash", config.MODEL_PRICES)

    def test_provider_by_prefix(self):
        self.assertEqual(provider_for("gemini-3.8-flash"), "gemini")
        self.assertEqual(provider_for("claude-opus-5-5"), "anthropic")
        self.assertEqual(provider_for("gpt-6-luna"), "unknown")

    def test_no_key_means_unavailable_and_no_call(self):
        fake = FakeTransport(ok_response({"authorizes_deletion": True}))
        with mock.patch.dict(os.environ, {}, clear=True):
            llm = LLM(Path(tempfile.mkdtemp()) / "c.json", enabled=True, transport=fake)
        self.assertFalse(llm.available_for("gemini-3.5-flash-lite"))
        self.assertIsNone(llm.json_call("gemini-3.5-flash-lite", "x", SCHEMA))
        self.assertEqual(fake.calls, [])

    def test_disabled_flag_ignores_key(self):
        with mock.patch.dict(os.environ, {config.GEMINI_API_KEY_ENV: "k"}):
            llm = LLM(Path(tempfile.mkdtemp()) / "c.json", enabled=False)
        self.assertFalse(llm.available_for("gemini-3.8-flash"))


class RequestShapeTests(unittest.TestCase):
    def test_text_request_body(self):
        fake = FakeTransport(ok_response({"authorizes_deletion": True}))
        llm = make_llm(fake)
        out = llm.json_call("gemini-3.5-flash-lite", "classify me", SCHEMA, max_tokens=1024, thinking_level="minimal")
        self.assertEqual(out, {"authorizes_deletion": True})
        url, body, headers = fake.calls[0]
        self.assertEqual(url, config.GEMINI_ENDPOINT)
        self.assertEqual(headers, {"x-goog-api-key": "test-key-not-real"})
        self.assertEqual(body["model"], "gemini-3.5-flash-lite")
        self.assertEqual(body["input"], [{"type": "text", "text": "classify me"}])
        self.assertEqual(body["response_format"], {"type": "text", "mime_type": "application/json", "schema": SCHEMA})
        self.assertEqual(body["generation_config"], {"max_output_tokens": 1024, "thinking_level": "minimal"})
        self.assertIs(body["store"], False)

    def test_image_request_body(self):
        fake = FakeTransport(ok_response({"authorizes_deletion": False}))
        llm = make_llm(fake)
        llm.json_call("gemini-3.8-flash", "read this", SCHEMA, image_png=b"\x89PNG fake", thinking_level="medium")
        image = fake.calls[0][1]["input"][1]
        self.assertEqual((image["type"], image["mime_type"], image["resolution"]), ("image", "image/png", "ultra_high"))
        self.assertTrue(image["data"])

    def test_cache_hit_makes_no_second_call(self):
        fake = FakeTransport(ok_response({"authorizes_deletion": True}))
        llm = make_llm(fake)
        llm.json_call("gemini-3.5-flash-lite", "same", SCHEMA)
        llm.json_call("gemini-3.5-flash-lite", "same", SCHEMA)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(llm.usage["cache_hits"], 1)


class FailSafeTests(unittest.TestCase):
    def test_http_error_returns_none(self):
        llm = make_llm(FakeTransport(exc=RuntimeError("HTTP 429")))
        self.assertIsNone(llm.json_call("gemini-3.5-flash-lite", "x", SCHEMA))

    def test_incomplete_or_failed_status_returns_none(self):
        for status in ("incomplete", "failed"):
            llm = make_llm(FakeTransport(ok_response({"authorizes_deletion": True}, status=status)))
            self.assertIsNone(llm.json_call("gemini-3.5-flash-lite", "x", SCHEMA))

    def test_bad_json_returns_none_and_is_not_cached(self):
        resp = {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "{oops"}]}],
                "usage": {}}
        llm = make_llm(FakeTransport(resp))
        self.assertIsNone(llm.json_call("gemini-3.5-flash-lite", "x", SCHEMA))
        self.assertEqual(llm.cache, {})


class UsageTests(unittest.TestCase):
    def test_thought_tokens_billed_at_output_rate(self):
        llm = make_llm(FakeTransport(ok_response({"authorizes_deletion": True},
                                                 usage={"total_input_tokens": 1_000_000, "total_output_tokens": 0,
                                                        "total_thought_tokens": 1_000_000})))
        llm.json_call("gemini-3.5-flash-lite", "x", SCHEMA)
        with tempfile.TemporaryDirectory() as d, mock.patch("audit.llm.USAGE_LEDGER", Path(d) / "ledger.json"):
            entry = llm.record_usage("test", 1)
        pin, pout = config.MODEL_PRICES["gemini-3.5-flash-lite"]
        self.assertAlmostEqual(entry["total_cost_usd"], pin + pout, places=6)


class IntentIntegrationTests(unittest.TestCase):
    def test_intent_fallback_uses_flash_lite_with_minimal_thinking_and_scrubbed_text(self):
        from audit.intent import classify
        fake = FakeTransport(ok_response({"authorizes_deletion": True, "request_type": "deletion"}))
        llm = make_llm(fake)
        authorized, flags, reason = classify("Bonjour, contactez-moi a jo@example.com svp.", False, llm)
        self.assertTrue(authorized)
        self.assertIn("INTENT_FROM_LLM", flags)
        body = fake.calls[0][1]
        self.assertEqual(body["model"], "gemini-3.5-flash-lite")
        self.assertEqual(body["generation_config"]["thinking_level"], "minimal")
        self.assertNotIn("jo@example.com", body["input"][0]["text"])


class ExtractionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import extract_images
        cls.ex = extract_images

    def test_model_records_are_closed_world_validated(self):
        known = ({"backup_9287"}, {"areed1433@gmail.com"}, {"user_16"}, {})
        raw = [{"resource_id": "backup_9287", "email": "areed1433@gmail.com", "customer_reference": "user_999",
                "result": "ACTIVE", "related_resource_ids": ["backup_1"]},
               {"resource_id": "backup_4242", "email": "x@y.com"},
               {"resource_id": "backup_9287", "email": "stranger@else.com"}]
        records, rejected = self.ex.validate_model_records(raw, known)
        self.assertEqual(records[0]["email"], "areed1433@gmail.com")
        self.assertNotIn("customer_reference", records[0])
        self.assertEqual(records[0]["related_resource_ids"], [])
        self.assertNotIn("email", records[1])
        self.assertIn("stranger@else.com", records[1]["note"])
        self.assertIn("backup_4242", rejected)

    def test_model_backend_cannot_overwrite_ocr_cache(self):
        rc = self.ex.main(["--backend", "gemini", "--allow-vision", "--out", str(config.CACHE_DIR / "image_facts.json")])
        self.assertEqual(rc, 2)

    def test_model_backend_needs_opt_in(self):
        self.assertEqual(self.ex.main(["--backend", "gemini"]), 2)

    def test_model_backend_without_key_is_blocked_before_sending(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.ex.main(["--backend", "gemini", "--allow-vision",
                                           "--out", str(Path(tempfile.mkdtemp()) / "x.json")]), 1)

    def test_compare_reports_field_mismatch(self):
        model = {"e1": {"records": [{"resource_id": "a_1", "email": "x@y.com"}, {"resource_id": "b_2"}]}}
        ocr = {"e1": {"records": [{"resource_id": "a_1", "email": "z@y.com"}]}}
        rep = self.ex.compare_with_ocr(model, ocr)["e1"]
        self.assertEqual(rep["only_model"], ["b_2"])
        self.assertEqual(rep["field_mismatch"][0]["field"], "email")


if __name__ == "__main__":
    unittest.main()

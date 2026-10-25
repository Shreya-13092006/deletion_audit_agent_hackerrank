"""Cross-platform and API robustness: pinned PDF text, loud PDF failures, planner targets, HTTP retries."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import agent_fixtures as af

from audit import config
from audit.agent.planner import GeminiPlanner
from audit.llm import LLM
from audit.parsers import documents as D

PDF = config.DATASET_DIR / "evidence" / "documents" / "security_retention_extract.pdf"


def no_extractor():
    """Simulate Windows PowerShell without poppler and without pypdf."""
    return mock.patch.multiple(D, _extract_pdf_text=lambda path: ("", "none"))


class PdfTextTests(unittest.TestCase):
    def test_pinned_text_is_used_without_any_extractor(self):
        shipped = json.loads((config.CACHE_DIR / "pdf_text.json").read_text(encoding="utf-8"))
        self.assertEqual(len(shipped), 4)
        with no_extractor():
            text = D.pdf_text(PDF)
        self.assertEqual(text, shipped[PDF.name]["text"])
        self.assertIn("audit_record", text)

    def test_unreadable_pdf_is_a_parse_error_not_silent_absence(self):
        empty_cache = Path(tempfile.mkdtemp()) / "pdf_text.json"
        with no_extractor(), mock.patch.object(D, "pdf_text_cache_path", lambda: empty_cache):
            with self.assertRaises(RuntimeError):
                D.parse_pdf(PDF, "evidence_x", "2026-09-01T00:00:00Z", {})
        self.assertFalse(empty_cache.exists())       # nothing empty was pinned

    def test_stale_cache_entry_is_not_used(self):
        tmp = Path(tempfile.mkdtemp()) / "pdf_text.json"
        tmp.write_text(json.dumps({PDF.name: {"sha256": "0" * 64, "text": "stale"}}), encoding="utf-8")
        with mock.patch.object(D, "_extract_pdf_text", lambda path: ("fresh text", "test")):
            self.assertEqual(D.pdf_text(PDF, tmp), "fresh text")
        self.assertEqual(json.loads(tmp.read_text(encoding="utf-8"))[PDF.name]["text"], "fresh text")


def reply(payload):
    return {"status": "completed", "usage": {"total_input_tokens": 100, "total_output_tokens": 10},
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}]}


class SeqTransport:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def __call__(self, url, body, headers):
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else self.last
        self.last = out
        if isinstance(out, Exception):
            raise out
        if callable(out):
            return out(body)
        return out


def make_llm(transport):
    with mock.patch.dict(os.environ, {config.GEMINI_API_KEY_ENV: "test-key-not-real",
                                      "AUDIT_LLM_RETRY_DELAYS": "0,0"}, clear=False):
        return LLM(Path(tempfile.mkdtemp()) / "c.json", enabled=True, transport=transport)


class ApiRobustnessTests(unittest.TestCase):
    SCHEMA = {"type": "object", "properties": {"x": {"type": "boolean"}}, "required": ["x"]}

    def test_transient_http_error_is_retried(self):
        t = SeqTransport(RuntimeError("HTTP 429"), RuntimeError("HTTP 503"), reply({"x": True}))
        llm = make_llm(t)
        self.assertEqual(llm.json_call("gemini-3.5-flash-lite", "p", self.SCHEMA), {"x": True})
        self.assertEqual(t.calls, 3)

    def test_permanent_http_error_is_not_retried(self):
        t = SeqTransport(RuntimeError("HTTP 400"))
        llm = make_llm(t)
        self.assertIsNone(llm.json_call("gemini-3.5-flash-lite", "p", self.SCHEMA))
        self.assertEqual(t.calls, 1)

    def test_case_level_none_target_is_accepted(self):
        """Regression: Gemini answered targets=["none"] for case-level gaps (110 rejections on 2026-10-25)."""
        def answer(body):
            tools = body["response_format"]["schema"]["properties"]["tool"]["enum"]
            return reply({"tool": tools[0], "targets": ["none"], "stop": False, "reason": "next"})
        from audit.agent.tools import build_registry
        registry = build_registry()
        planner = GeminiPlanner(registry, make_llm(SeqTransport(answer)))
        _, _, _, cases = af.env()
        decision, card = af.orchestrator(planner=planner, registry=registry).run(cases["case_12"])
        self.assertEqual(planner.rejections, 0)
        self.assertTrue(all(t["planner"] == "gemini" for t in card["tool_calls"]))
        self.assertEqual(decision.steps, af.env()[1].audit(cases["case_12"]).steps)


if __name__ == "__main__":
    unittest.main()

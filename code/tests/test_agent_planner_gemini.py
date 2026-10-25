"""Gemini planner (offline fake transport): validated choices, PII-free prompts, fail-safe fallbacks."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import agent_fixtures as af

from audit import config
from audit.agent.planner import GeminiPlanner
from audit.agent.tools import build_registry
from audit.llm import LLM


def reply(payload):
    return {"status": "completed", "usage": {"total_input_tokens": 500, "total_output_tokens": 40},
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}]}


class ReverseTransport:
    """Picks the LAST allowed tool (opposite of the rule order) with no targets."""
    def __init__(self):
        self.bodies = []

    def __call__(self, url, body, headers):
        self.bodies.append(body)
        tools = body["response_format"]["schema"]["properties"]["tool"]["enum"]
        return reply({"tool": tools[-1], "targets": [], "stop": False, "reason": "explore risks first"})


class FixedTransport:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, 0

    def __call__(self, url, body, headers):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.response


def make(transport, key="test-key-not-real"):
    env = {"AUDIT_LLM_RETRY_DELAYS": "0,0", **({config.GEMINI_API_KEY_ENV: key} if key else {})}
    with mock.patch.dict(os.environ, env, clear=False):
        if not key:
            os.environ.pop(config.GEMINI_API_KEY_ENV, None)
        llm = LLM(Path(tempfile.mkdtemp()) / "planner_cache.json", enabled=True, transport=transport)
    registry = build_registry()
    return GeminiPlanner(registry, llm), registry


class GeminiPlannerTests(unittest.TestCase):
    def setUp(self):
        _, self.auditor, _, self.cases = af.env()

    def test_model_order_differs_but_decision_is_identical(self):
        transport = ReverseTransport()
        planner, registry = make(transport)
        orch = af.orchestrator(planner=planner, registry=registry)
        for cid in ("case_12", "case_16", "case_04"):
            decision, card = orch.run(self.cases[cid])
            engine = self.auditor.audit(self.cases[cid])
            self.assertEqual((decision.status, decision.steps), (engine.status, engine.steps), cid)
            self.assertEqual(card["decision"]["source"], "agent")
            self.assertTrue(any(t["planner"] == "gemini" for t in card["tool_calls"]))
        self.assertGreater(planner.llm.usage["calls"], 0)
        self.assertEqual(planner.llm.usage["by_model"][config.PLANNER_MODEL]["input_tokens"],
                         500 * planner.llm.usage["calls"])

    def test_prompt_contains_no_identifiers(self):
        transport = ReverseTransport()
        planner, registry = make(transport)
        af.orchestrator(planner=planner, registry=registry).run(self.cases["case_12"])
        blob = json.dumps(transport.bodies)
        self.assertNotRegex(blob, r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
        self.assertIsNone(re.search(r"\b(account|search|analytics|support|audit_record|user)_\d+\b", blob))
        self.assertIsNone(re.search(r"\b[0-9a-f]{64}\b", blob))

    def test_disallowed_tool_is_rejected(self):
        planner, registry = make(FixedTransport(reply({"tool": "verify_plan", "targets": [], "stop": False,
                                                       "reason": "skip"})))
        decision, card = af.orchestrator(planner=planner, registry=registry).run(self.cases["case_12"])
        self.assertTrue(all(t["planner"] in ("rule_fallback", "gemini") for t in card["tool_calls"]))
        self.assertEqual(card["tool_calls"][0]["tool"], "resolve_identity")
        self.assertGreater(planner.rejections, 0)
        self.assertEqual(decision.steps, self.auditor.audit(self.cases["case_12"]).steps)

    def test_premature_stop_is_overridden(self):
        planner, registry = make(FixedTransport(reply({"tool": "resolve_identity", "targets": [], "stop": True,
                                                       "reason": "done"})))
        _, card = af.orchestrator(planner=planner, registry=registry).run(self.cases["case_01"])
        self.assertEqual(card["decision"]["source"], "agent")
        self.assertEqual(card["tool_calls"][-1]["tool"], "verify_plan")

    def test_api_error_bad_json_and_no_key_fall_back(self):
        for transport, key in ((FixedTransport(exc=RuntimeError("HTTP 503")), "k"),
                               (FixedTransport({"status": "completed", "steps": [{"type": "model_output",
                                               "content": [{"type": "text", "text": "{oops"}]}], "usage": {}}), "k"),
                               (FixedTransport(reply({})), None)):
            planner, registry = make(transport, key)
            decision, card = af.orchestrator(planner=planner, registry=registry).run(self.cases["case_12"])
            self.assertEqual(decision.steps, self.auditor.audit(self.cases["case_12"]).steps)
            self.assertTrue(all(t["planner"] == "rule_fallback" for t in card["tool_calls"]))
        self.assertEqual(transport.calls, 0)        # no key: nothing is sent

    def test_per_case_model_budget(self):
        planner, registry = make(ReverseTransport())
        planner.per_case = 2
        _, card = af.orchestrator(planner=planner, registry=registry).run(self.cases["case_12"])
        self.assertEqual(card["budget"]["model_calls"], 2)
        self.assertTrue(any(t["planner"] == "rule_fallback" for t in card["tool_calls"]))


if __name__ == "__main__":
    unittest.main()

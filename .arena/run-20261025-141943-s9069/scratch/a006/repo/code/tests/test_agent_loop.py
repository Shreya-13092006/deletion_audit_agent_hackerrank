"""Agent loop: parity with the engine, gap order, stop conditions, fallback, case cards, contradictions."""
import json
import unittest

import agent_fixtures as af
from helpers import obs

from audit import config
from audit.agent.loop import Budget
from audit.aliases import extract_identifiers
from audit.identity import IdentityGraph, email_hash
from audit.parsers.common import record_observation
from audit.pipeline import load_cases
from audit.policy import retention_condition
from audit.schema import Identity
from audit.state import ResourceState
from audit.trail import AuditTrail

# af.env() keys cases by case_id, so case_01..case_32 are the public samples (loaded last).
SAMPLE_IDS = {c.case_id for c in load_cases(config.DATASET_DIR / "sample_deletion_requests.csv")}


class LoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orch = af.orchestrator()
        _, cls.auditor, _, cls.cases = af.env()
        cls.results = {cid: cls.orch.run(c) for cid, c in sorted(cls.cases.items())}

    def test_parity_with_engine_for_every_case(self):
        # The agent equals the engine except where a proof gate downgraded an unproven COMPLETE.
        for cid, (decision, card) in self.results.items():
            engine = self.auditor.audit(self.cases[cid])
            if card["decision"]["source"] == "agent+proof_downgrade":
                self.assertEqual((engine.status, decision.status), ("COMPLETE", "INCOMPLETE"), cid)
                self.assertTrue(any(f.startswith("AGENT_PROOF_DOWNGRADE:") for f in card["flags"]), cid)
                self.assertTrue(card["review"]["required"], cid)
                self.assertTrue(all(s.phase == "VERIFICATION" and s.evidence_id == "" for s in decision.steps), cid)
                continue
            self.assertEqual((decision.status, decision.steps), (engine.status, engine.steps), cid)
            self.assertEqual(card["decision"]["source"], "agent", cid)

    def test_downgrades_are_only_unproven_primary_accounts_and_no_sample_changes(self):
        down = {cid: card for cid, (_, card) in self.results.items()
                if card["decision"]["source"].endswith("+proof_downgrade")}
        self.assertFalse([cid for cid in down if cid in SAMPLE_IDS])
        self.assertTrue(down)
        for cid, card in down.items():
            self.assertTrue(any(":primary_account_unproven:" in f for f in card["proof"]["failures"]), cid)

    def test_no_unsupported_claims_fallbacks_or_exhaustion(self):
        s = self.orch.stats
        self.assertEqual((s["unsupported_claims"], s["fallbacks"], s["parity_diffs"], s["exhausted"]), (0, 0, 0, 0))

    def test_gap_driven_order(self):
        _, card = self.results["case_12"]
        tools = [t["tool"] for t in card["tool_calls"]]
        self.assertEqual(tools[:5], ["resolve_identity", "search_evidence", "follow_links", "classify_intent",
                                     "attribute_workflow"])
        self.assertEqual(tools[5], "reconstruct_timeline")
        self.assertEqual(tools[-1], "verify_plan")
        self.assertEqual(card["budget"]["stop_reason"], "sufficient: no open gaps")
        self.assertEqual(card["gaps"]["open"], [])

    def test_not_applicable_stops_after_intent(self):
        na = [card for _, card in self.results.values() if card["decision"]["status"] == "NOT_APPLICABLE"]
        self.assertEqual(len(na), 10)
        for card in na:
            self.assertEqual(card["tool_calls"][-1]["tool"], "classify_intent")
            self.assertEqual(card["decision"]["steps"], [])

    def test_case12_historical_hash_and_identity_provenance(self):
        _, card = self.results["case_12"]
        self.assertEqual(card["identity"]["status"], "RESOLVED")
        self.assertTrue(any(p["source"].startswith("user_audit_log.csv") for p in card["identity"]["provenance"]))
        self.assertIn("analytics_9914", card["resources"])

    def test_replica_drift_contradiction_case16(self):
        _, card = self.results["case_16"]
        drift = [c for c in card["contradictions"] if c["kind"] == "primary_vs_replica"]
        self.assertTrue(drift)
        self.assertEqual(drift[0]["resource_id"], "account_994")
        self.assertEqual(drift[0]["copies"]["customer_data_primary"], "MISSING")
        self.assertEqual(drift[0]["resolution"], "any_replica_present")

    def test_claim_vs_evidence_is_surfaced(self):
        kinds = {c["kind"] for _, card in self.results.values() for c in card["contradictions"]}
        self.assertIn("claim_vs_evidence", kinds)

    def test_case_cards_serializable_and_deterministic(self):
        again = af.orchestrator().run(self.cases["case_23"])[1]
        self.assertEqual(json.dumps(self.results["case_23"][1], sort_keys=True), json.dumps(again, sort_keys=True))
        self.assertTrue(self.results["case_23"][1]["review"]["required"])   # time-only tie -> human review

    def test_budget_exhaustion_falls_back_to_engine(self):
        orch = af.orchestrator(budget=Budget(max_iterations=3, max_tool_calls=3))
        case = self.cases["case_12"]
        decision, card = orch.run(case)
        engine = self.auditor.audit(case)
        self.assertEqual((decision.status, decision.steps), (engine.status, engine.steps))
        self.assertEqual(card["decision"]["source"], "fallback")
        self.assertIn("AGENT_BUDGET_EXHAUSTED", card["flags"])
        self.assertTrue(card["budget"]["exhausted"])

    def test_trail_records_tool_calls_without_secrets(self):
        trail = AuditTrail(None)
        af.orchestrator(trail=trail).run(self.cases["case_01"])
        events = [e["event"] for e in trail.entries]
        self.assertIn("tool_call", events)
        self.assertIn("agent_decision", events)
        blob = json.dumps(trail.entries)
        self.assertNotIn("API_KEY", blob)
        self.assertNotIn("x-goog-api-key", blob)


class SmallFixTests(unittest.TestCase):
    def test_zero_hit_search_query_carries_the_email(self):
        ids = extract_identifiers({"resource_id": "search_1", "query": "A.B@x.com"})
        self.assertEqual(ids["emails"], {"a.b@x.com"})
        o = record_observation({"resource_id": "search_1", "query": "a.b@x.com"}, evidence_id="e",
                               observed_at="t", captured_at="t", collection="customer_search_documents", source="s")
        self.assertEqual(o.emails, {"a.b@x.com"})

    def test_retention_condition(self):
        def rs(rtype, **attrs):
            return ResourceState("audit_record_1", "security_service", rtype, "PRESENT", None, "e", attrs=attrs)
        at = "2026-09-01T00:00:00Z"
        self.assertEqual(retention_condition(rs("SECURITY_AUDIT_LOG", retention_until="2031-12-31T23:59:59Z"), at)[0], True)
        self.assertEqual(retention_condition(rs("SECURITY_AUDIT_LOG", retention_until="2026-01-01T00:00:00Z"), at)[0], False)
        self.assertIsNone(retention_condition(rs("SECURITY_AUDIT_LOG"), at)[0])
        self.assertEqual(retention_condition(rs("LEGAL_HOLD_RECORD", retained_until="2033-12-31T23:59:59Z"), at)[0], True)
        self.assertEqual(retention_condition(rs("LEGAL_HOLD_RECORD", hold_status="RELEASED"), at)[0], False)

    def test_identity_hash_mismatch_is_recorded(self):
        i = Identity("user_1", {"a@x.com"}, {email_hash("a@x.com")}, set(), set())
        i._hash_mismatch = True
        self.assertEqual(IdentityGraph({"user_1": i}).hash_mismatches, {"user_1"})
        self.assertEqual(af.env()[1].graph.hash_mismatches, set())      # shipped dataset: none

    def test_stale_reading_still_respected_by_agent(self):
        # helpers.obs smoke: the agent reuses state.resolve, so the 14-day horizon applies unchanged
        from audit.state import resolve
        r = resolve("export_1", [obs("export_1", at="2026-01-01T00:00:00Z")], [], "2026-09-01T00:00:00Z", 14)
        self.assertEqual(r.state, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

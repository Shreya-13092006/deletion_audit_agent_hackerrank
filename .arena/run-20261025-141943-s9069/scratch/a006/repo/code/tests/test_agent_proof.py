"""Proof gates (G3 state support, G9 completion proof), the COMPLETE->INCOMPLETE fail-safe,
corroboration with a genuine `unresolved` outcome, and unverified success claims.

All cases are synthetic (fictional identity user_900 / rowan.vale@example.test, from
evaluation/custom_cases.py); the expected results are written by hand from the rules.
"""
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts code/ on sys.path)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
from custom_cases import AUDIT, build_auditor, case, o  # noqa: E402

from audit.agent.gates import check_step, completion_proof  # noqa: E402
from audit.agent.loop import Budget, Orchestrator  # noqa: E402
from audit.agent.planner import RulePlanner  # noqa: E402
from audit.agent.state import CaseState  # noqa: E402
from audit.agent.tools import ToolContext, build_registry  # noqa: E402
from audit.schema import Step  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402

ME = {"emails": {"rowan.vale@example.test"}}
FRESH = "2026-09-19T10:00:00Z"            # 1 day before AUDIT
OLDER = "2026-09-15T10:00:00Z"
STALE = "2026-08-20T10:00:00Z"            # > 14 days before AUDIT
LATER = "2026-09-25T10:00:00Z"            # after AUDIT


def step(op, rid, ev, state=None):
    from audit.aliases import system_for
    from audit.config import OPERATION_PHASE, OPERATION_STATE
    return Step(OPERATION_PHASE[op], system_for(rid), rid, op, state or OPERATION_STATE[op], ev)


def run_agent(a, c=None):
    for ob in a.store.observations:            # register the synthetic evidence files
        a.store.manifest.setdefault(ob.evidence_id, {"file_id": ob.evidence_id, "captured_at": ob.captured_at})
    registry = build_registry()
    orch = Orchestrator(ToolContext(a), registry, RulePlanner(registry), AuditTrail(None), Budget())
    return orch.run(c or case("Please delete my account."))


class ClaimSupportTests(unittest.TestCase):
    def test_cited_file_must_show_the_claimed_state(self):
        a = build_auditor([o("ev_p", FRESH, "account_83", "PRESENT", "USER_PROFILE", **ME)])
        self.assertEqual(check_step(a, step("VERIFY_RECORD_ABSENT", "account_83", "ev_p"), AUDIT), "state_mismatch")
        self.assertEqual(check_step(a, step("REPORT_REMAINING_RECORD", "account_83", "ev_p"), AUDIT), "")

    def test_stale_reading_is_not_proof(self):
        a = build_auditor([o("ev_s", STALE, "account_83", "ABSENT", "USER_PROFILE", **ME)])
        self.assertEqual(check_step(a, step("VERIFY_RECORD_ABSENT", "account_83", "ev_s"), AUDIT), "stale_evidence")

    def test_evidence_after_audit_is_not_proof(self):
        a = build_auditor([o("ev_l", LATER, "account_83", "ABSENT", "USER_PROFILE", **ME)])
        self.assertEqual(check_step(a, step("VERIFY_RECORD_ABSENT", "account_83", "ev_l"), AUDIT), "no_matching_fact")

    def test_later_reading_before_audit_supersedes_the_citation(self):
        a = build_auditor([o("ev_a", OLDER, "search_83", "ABSENT", "SEARCH_INDEX_ENTRY", **ME),
                           o("ev_b", FRESH, "search_83", "PRESENT", "SEARCH_INDEX_ENTRY", **ME)])
        self.assertEqual(check_step(a, step("VERIFY_RECORD_ABSENT", "search_83", "ev_a"), AUDIT),
                         "superseded_before_audit")

    def test_any_copy_present_in_the_cited_snapshot_blocks_an_absence_claim(self):
        primary = o("ev_r", FRESH, "account_83", "ABSENT", "USER_PROFILE", **ME)
        replica = o("ev_r", FRESH, "account_83", "PRESENT", "USER_PROFILE", **ME)
        primary.replica, replica.replica = "customer_data_primary", "read_replica"
        a = build_auditor([primary, replica])
        self.assertEqual(check_step(a, step("VERIFY_RECORD_ABSENT", "account_83", "ev_r"), AUDIT),
                         "state_mismatch:other_copy")

    def test_redaction_claim_needs_identifiers_removed(self):
        a = build_auditor([o("ev_m", FRESH, "support_83", "PRESENT", "SUPPORT_MESSAGE", True, **ME)])
        self.assertEqual(check_step(a, step("VERIFY_RECORD_REDACTED", "support_83", "ev_m"), AUDIT), "pii_mismatch")
        self.assertEqual(check_step(a, step("REPORT_EXPOSED_PII", "support_83", "ev_m"), AUDIT), "")

    def test_unreadable_evidence_is_never_proof(self):
        a = build_auditor([o("ev_u", FRESH, "account_83", "ABSENT", "USER_PROFILE", **ME)])
        a.store.errors.append(("ev_u", "ValueError('truncated')"))
        self.assertEqual(check_step(a, step("VERIFY_RECORD_ABSENT", "account_83", "ev_u"), AUDIT),
                         "unreadable_evidence")


class CompletionProofTests(unittest.TestCase):
    def proof(self, a, linked, primary, steps):
        st = CaseState(case("Please delete my account."))
        return completion_proof(ToolContext(a), st, "COMPLETE", steps, linked, primary)

    def test_unproven_primary_account_fails(self):
        a = build_auditor([o("ev_l", LATER, "account_83", "ABSENT", "USER_PROFILE", **ME)])
        failures, _, _ = self.proof(a, {"account_83"}, "account_83", [])
        self.assertEqual(failures, ["account_83:primary_account_unproven:only_later_evidence"])

    def test_record_known_only_from_later_evidence_is_accounted_not_proof(self):
        a = build_auditor([o("ev_l", LATER, "search_83", "PRESENT", "SEARCH_INDEX_ENTRY", **ME)])
        failures, accounting, _ = self.proof(a, {"search_83"}, None, [])
        self.assertEqual((failures, accounting), ([], {"search_83": "only_later_evidence"}))

    def test_stale_record_and_active_flow_and_unknown_pii_fail(self):
        a = build_auditor([o("ev_s", STALE, "search_83", "PRESENT", "SEARCH_INDEX_ENTRY", **ME),
                           o("ev_f", FRESH, "connector_83", "ACTIVE", "DATA_FLOW", **ME),
                           o("ev_m", FRESH, "support_83", "PRESENT", "SUPPORT_MESSAGE", None, **ME)])
        failures, _, _ = self.proof(a, {"search_83", "connector_83", "support_83"}, None, [])
        self.assertEqual(sorted(failures), ["connector_83:active_recreation_path", "search_83:stale_evidence",
                                            "support_83:pii_unknown"])

    def test_missing_retained_record_and_wrong_treatment_fail(self):
        a = build_auditor([o("ev_a", FRESH, "audit_record_83", "ABSENT", "SECURITY_AUDIT_LOG", users={"user_900"}),
                           o("ev_n", FRESH, "analytics_83", "PRESENT", "ANALYTICS_PROFILE", False, **ME)])
        wrong = step("VERIFY_RECORD_ABSENT", "analytics_83", "ev_n")
        failures, _, _ = self.proof(a, {"audit_record_83", "analytics_83"}, None, [wrong])
        self.assertIn("audit_record_83:retained_record_absent", failures)
        self.assertTrue(any(f.startswith("analytics_83:wrong_treatment") for f in failures))


class FailSafeTests(unittest.TestCase):
    def test_unproven_complete_is_downgraded_and_flagged(self):
        # Workflow claims the profile was deleted; the only profile reading is in a later file.
        late = o("ev_late", FRESH, "account_86", "ABSENT", "USER_PROFILE", **ME)
        late.captured_at = LATER
        a = build_auditor([late, o("ev_k", FRESH, "audit_record_86", "PRESENT", "SECURITY_AUDIT_LOG",
                                   users={"user_900"})])
        a.store.activity.by_resource = {"account_86": [{
            "activity_id": "activity_86", "event_time": "2026-09-11T11:00:00Z", "event_type": "DELETE_RECORD",
            "reported_result": "SUCCESS", "source_system": "deletion_worker", "target_system": "account_service",
            "resource_id": "account_86", "details": "Deleted account_86."}]}
        engine = a.audit(case("Please delete my account."))
        self.assertEqual(engine.status, "COMPLETE")                 # the unverified engine answer
        d, card = run_agent(a)
        self.assertEqual(d.status, "INCOMPLETE")
        self.assertEqual(card["decision"]["source"], "agent+proof_downgrade")
        self.assertIn("AGENT_PROOF_DOWNGRADE:G9_completion_proof", card["flags"])
        self.assertTrue(card["review"]["required"])
        self.assertEqual([(s.operation, s.resource_id, s.evidence_id) for s in d.steps],
                         [("VERIFY_RECORD_ABSENT", "account_86", ""), ("VERIFY_RECORD_PRESENT", "audit_record_86", "")])
        claim = [c for c in card["contradictions"] if c["kind"] == "claim_unverified"]
        self.assertEqual(claim[0]["resolution"], "unresolved")

    def test_engine_fallback_is_proof_checked_too(self):
        late = o("ev_late", FRESH, "account_87", "ABSENT", "USER_PROFILE", **ME)
        late.captured_at = LATER
        a = build_auditor([late, o("ev_k", FRESH, "audit_record_87", "PRESENT", "SECURITY_AUDIT_LOG",
                                   users={"user_900"})])
        for ob in a.store.observations:
            a.store.manifest.setdefault(ob.evidence_id, {"file_id": ob.evidence_id, "captured_at": ob.captured_at})
        registry = build_registry()
        orch = Orchestrator(ToolContext(a), registry, RulePlanner(registry), AuditTrail(None),
                            Budget(max_iterations=2, max_tool_calls=2))
        d, card = orch.run(case("Please delete my account."))
        self.assertEqual(card["decision"]["source"], "fallback+proof_downgrade")
        self.assertEqual(d.status, "INCOMPLETE")


class CorroborationTests(unittest.TestCase):
    def test_independent_files_disagreeing_at_the_same_time_stay_unresolved(self):
        a = build_auditor([o("ev_x", FRESH, "search_88", "PRESENT", "SEARCH_INDEX_ENTRY", **ME),
                           o("ev_y", FRESH, "search_88", "ABSENT", "SEARCH_INDEX_ENTRY", **ME),
                           o("ev_z", FRESH, "account_88", "ABSENT", "USER_PROFILE", **ME)])
        d, card = run_agent(a)
        conflict = [c for c in card["contradictions"] if c["kind"] == "same_time_existence_conflict"]
        self.assertEqual(len(conflict), 1)
        self.assertEqual((conflict[0]["resolution"], conflict[0]["evidence"]), ("unresolved", ["ev_x", "ev_y"]))
        self.assertEqual(len(conflict[0]["sources"]), 2)                   # both readings kept with provenance
        self.assertIn("corroborate_evidence", [t["tool"] for t in card["tool_calls"]])
        self.assertIn("CONTRADICTION_UNRESOLVED:search_88", card["review"]["reasons"])
        self.assertEqual(d.status, "INCOMPLETE")       # conservative: any copy present means present

    def test_timeline_change_is_corroborated_and_resolved_by_latest_reading(self):
        a = build_auditor([o("ev_a", OLDER, "search_89", "PRESENT", "SEARCH_INDEX_ENTRY", **ME),
                           o("ev_b", FRESH, "search_89", "ABSENT", "SEARCH_INDEX_ENTRY", **ME),
                           o("ev_b", FRESH, "account_89", "ABSENT", "USER_PROFILE", **ME)])
        _, card = run_agent(a)
        flip = [c for c in card["contradictions"] if c["kind"] == "found_then_not_found"][0]
        self.assertEqual(flip["resolution"], "latest_valid")
        self.assertEqual([s["evidence_id"] for s in flip["sources"]], ["ev_a", "ev_b"])

    def test_unverified_claim_consistent_with_evidence_is_recorded_not_flagged(self):
        a = build_auditor([o("ev_c", OLDER, "account_90", "ABSENT", "USER_PROFILE", **ME)])
        a.store.activity.by_resource = {"account_90": [{
            "activity_id": "activity_90", "event_time": "2026-09-16T11:00:00Z", "event_type": "DELETE_RECORD",
            "reported_result": "SUCCESS", "source_system": "deletion_worker", "target_system": "account_service",
            "resource_id": "account_90", "details": "Deleted account_90."}]}
        _, card = run_agent(a)
        claim = [c for c in card["contradictions"] if c["kind"] == "claim_unverified"][0]
        self.assertEqual(claim["resolution"], "consistent_with_prior_evidence")


if __name__ == "__main__":
    unittest.main()

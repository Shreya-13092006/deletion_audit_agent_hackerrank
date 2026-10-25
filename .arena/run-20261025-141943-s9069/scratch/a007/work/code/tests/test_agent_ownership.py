"""Ownership tiers, G10, snapshot-scope classification, evidence gaps and miss classification.

Ownership and state are separate questions; tiers describe how ownership was established and
never by themselves make a step invalid (only G10: a FINDING needs `proven` ownership).
"""
import sys
import unittest
from pathlib import Path

import agent_fixtures as af
import helpers  # noqa: F401
from helpers import real_auditor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
from custom_cases import build_auditor, case, o  # noqa: E402

from audit import guardrails as g  # noqa: E402
from audit.agent.ownership import (classify_miss, evidence_gaps, g10_ownership, omission_scope_flags,  # noqa: E402
                                   ownership, policy_category_conflicts, scope_kind)
from audit.agent.state import CaseState  # noqa: E402
from audit.agent.tools import ToolContext  # noqa: E402
from audit.state import ResourceState  # noqa: E402
from test_agent_proof import ME, FRESH, run_agent  # noqa: E402


def st_with(linked, primary=None, flags=()):
    st = CaseState(case("Please delete my account."))
    st.linked = {rid: (rid, reason, ev) for rid, (reason, ev) in linked.items()}
    st.primary, st.flags = primary, list(flags)
    return st


class TierTests(unittest.TestCase):
    def test_each_tier(self):
        st = st_with({"account_1": ("workflow_attribution", ""), "analytics_1": ("workflow_attribution", ""),
                      "search_1": ("identifier", "ev_a"), "search_2": ("identifier_later_evidence", "ev_l"),
                      "account_2": ("resource_link:search_1", "ev_a"), "account_3": ("resource_link:search_2", "ev_l"),
                      "data_flow_1": ("repopulates:search_1", "activity_1")},
                     primary="account_1", flags=[g.FLAG_ACCOUNT_TIE])
        tiers = {rid: ownership(st, rid)["tier"] for rid in st.linked}
        self.assertEqual(tiers, {"account_1": "contested", "analytics_1": "inferred", "search_1": "proven",
                                 "search_2": "proven-later", "account_2": "proven", "account_3": "proven-later",
                                 "data_flow_1": "proven"})

    def test_attributed_primary_without_tie_is_inferred(self):
        st = st_with({"account_1": ("workflow_attribution", "")}, primary="account_1")
        self.assertEqual(ownership(st, "account_1")["tier"], "inferred")


class G10Tests(unittest.TestCase):
    def test_g10_rejects_only_findings_without_proven_ownership(self):
        audit = [{"phase": "FINDING", "resource_id": "search_1", "ownership": {"tier": "proven"}},
                 {"phase": "FINDING", "resource_id": "analytics_1", "ownership": {"tier": "inferred"}},
                 {"phase": "FINDING", "resource_id": "search_2", "ownership": {"tier": "proven-later"}},
                 {"phase": "VERIFICATION", "resource_id": "account_1", "ownership": {"tier": "contested"}}]
        self.assertEqual(g10_ownership(audit), ["analytics_1:inferred", "search_2:proven-later"])

    def test_g10_flags_for_review_and_never_changes_the_decision(self):
        # A record with no identifier, attributed to the case by the workflow, still shows PII.
        a = build_auditor([o("ev_w", FRESH, "account_91", "ABSENT", "USER_PROFILE", **ME),
                           o("ev_w", FRESH, "search_91", "PRESENT", "SEARCH_INDEX_ENTRY")])
        a.workflow_resources = {"custom": {"search_91"}}
        engine = a.audit(case("Please delete my account."))
        d, card = run_agent(a)
        self.assertEqual((d.status, d.steps), (engine.status, engine.steps))       # output untouched
        self.assertTrue(card["gates"]["G10_finding_ownership"].startswith("fail:search_91:inferred"))
        self.assertIn("AGENT_OWNERSHIP_UNPROVEN_FINDING", card["flags"])
        self.assertTrue(card["review"]["required"])
        finding = [x for x in card["step_audit"] if x["resource_id"] == "search_91" and x["phase"] == "FINDING"][0]
        self.assertEqual(finding["ownership"]["tier"], "inferred")
        self.assertEqual(finding["state"]["basis"], "direct")                       # state is a separate answer

    def test_inferred_verification_steps_are_kept(self):
        a = build_auditor([o("ev_w", FRESH, "account_92", "ABSENT", "USER_PROFILE"),
                           o("ev_w", FRESH, "audit_record_92", "PRESENT", "SECURITY_AUDIT_LOG", users={"user_900"})])
        a.workflow_resources = {"custom": {"account_92"}}
        d, card = run_agent(a)
        self.assertIn(("VERIFY_RECORD_ABSENT", "account_92"), [(s.operation, s.resource_id) for s in d.steps])
        self.assertEqual(card["gates"]["G10_finding_ownership"], "pass")


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, _ = real_auditor()

    def test_inventory_snapshot_scope_is_declared(self):
        k = scope_kind(self.a, "evidence_75", "account_service")      # customer_data_inventory_20260524.sql
        self.assertEqual((k["scope"], k["targeted"]), ("declared", False))
        self.assertEqual(scope_kind(self.a, "evidence_75", "no_such_service")["scope"], "not_covered")

    def test_failover_pair_scope_is_inferred_and_targeted(self):
        k = scope_kind(self.a, "evidence_54", "account_service")      # customer_accounts_failover_replica_20260902.sql
        self.assertEqual(k, {"scope": "inferred", "records_of_system": 4, "targeted": True})

    def test_bundle_data_store_is_declared(self):
        self.assertEqual(scope_kind(self.a, "evidence_51", "account_service")["scope"], "declared")

    def test_undeclared_omission_scopes_are_flagged_even_when_policy_accepts(self):
        def om(rid, scope, verdict):
            return {"resource_id": rid, "state": {"basis": "omission", "scope": scope, "targeted": True,
                                                   "records_of_system": 4, "policy": {"verdict": verdict}}}
        audit = [om("account_1", "inferred", "accepted"), om("account_2", "inferred", "accepted_single_system_snapshot"),
                 om("account_3", "declared", "declared_scope"),
                 om("account_4", "inferred", "conditions_unmet:requester_in_capture"),
                 {"resource_id": "search_1", "state": {"basis": "direct"}}]
        self.assertEqual(omission_scope_flags(audit), [
            "account_1:inferred:accepted",
            "account_2:inferred:accepted_single_system_snapshot",
            "account_4:inferred:conditions_unmet:requester_in_capture",
        ])


class EvidenceGapTests(unittest.TestCase):
    def test_gap_kinds(self):
        a = build_auditor([])
        a.tied_resources = {"custom": {"analytics_5"}, "case_x": {"analytics_5"}}
        a.ambiguous_accounts = {"custom": ["account_7"]}
        st = st_with({"audit_record_9": ("identifier", "ev")})
        st.identity = object()
        st.resources = {"audit_record_9": ResourceState("audit_record_9", "security_service", "SECURITY_AUDIT_LOG",
                                                        "UNKNOWN", None, "")}
        kinds = [x["kind"] for x in evidence_gaps(ToolContext(a), st)]
        self.assertEqual(kinds, ["primary_account_not_identified", "workflow_tie", "account_time_only_tie",
                                 "retained_record_unreadable"])
        st.resources = {}
        self.assertIn("no_security_audit_record", [x["kind"] for x in evidence_gaps(ToolContext(a), st)])

    def test_not_applicable_case_has_no_gaps(self):
        st = st_with({})
        st.not_applicable = True
        self.assertEqual(evidence_gaps(ToolContext(build_auditor([])), st), [])

    def test_gaps_live_on_the_card_not_in_the_output_steps(self):
        a = build_auditor([o("ev_g", FRESH, "account_93", "ABSENT", "USER_PROFILE", **ME)])
        d, card = run_agent(a)
        self.assertIn("no_security_audit_record", [x["kind"] for x in card["evidence_gaps"]])
        self.assertNotIn("audit_record", " ".join(s.resource_id for s in d.steps))


class MissClassificationTests(unittest.TestCase):
    def test_three_reasons(self):
        text = "... account_5 seen here ..."
        self.assertEqual(classify_miss("analytics_1", "c1", text, {"c1": {"analytics_1"}}, {}), "tie")
        self.assertEqual(classify_miss("account_410", "c1", text, {}, {"c1": ["account_410"]}), "tie")
        self.assertEqual(classify_miss("audit_record_6645", "c1", text, {}, {}), "not_discoverable")
        self.assertEqual(classify_miss("account_5", "c1", text, {}, {}), "parser_or_search_error")

    def test_every_case_card_answers_both_questions_for_every_step(self):
        orch = af.orchestrator()
        _, _, _, cases = af.env()
        for cid in ("case_01", "case_12", "case_16", "case_23", "case_31"):
            d, card = orch.run(cases[cid])
            self.assertEqual(len(card["step_audit"]), len(d.steps), cid)
            for x in card["step_audit"]:
                self.assertIn(x["ownership"]["tier"], ("proven", "proven-later", "inferred", "contested"), cid)
                self.assertIn(x["state"]["basis"], ("direct", "omission", "future"), cid)
            self.assertEqual(card["gates"]["G10_finding_ownership"], "pass", cid)
        self.assertEqual({x["ownership"]["tier"] for x in orch.run(cases["case_23"])[1]["step_audit"]
                          if x["resource_id"] == "account_9155"}, {"contested"})


class OmissionPolicyTests(unittest.TestCase):
    """Absence-by-omission from a snapshot without a declared scope (four conditions)."""
    AT = "2026-09-20T09:00:00Z"            # synthetic capture time, inside the window of AUDIT

    def setup(self, covers, extra=(), requester_in_file=True, at=None):
        from audit.schema import ScopeCover
        at = at or self.AT
        obs = [o("ev_snap", at, "account_55", "PRESENT", "USER_PROFILE")]               # system has rows in the file
        if requester_in_file:
            obs.append(o("ev_snap", at, "search_95", "PRESENT", "SEARCH_INDEX_ENTRY", **ME))
        a = build_auditor(obs + list(extra), covers=[ScopeCover("ev_snap", at, s, frozenset(r)) for s, r in covers])
        st = st_with({"account_95": ("workflow_attribution", ""), "search_95": ("identifier", "ev_snap")},
                     primary="account_95")
        return a, st

    def verdict(self, a, st):
        from audit.agent.ownership import scope_kind, omission_policy
        from audit.schema import Step
        step = Step("VERIFICATION", "account_service", "account_95", "VERIFY_RECORD_ABSENT", "ABSENT", "ev_snap")
        return omission_policy(a, st, step, scope_kind(a, "ev_snap", "account_service"), "2026-09-20T12:00:00Z")

    def test_all_four_conditions_accept(self):
        a, st = self.setup([("account_service", {"account_55"}), ("search_service", {"search_95"})])
        v = self.verdict(a, st)
        self.assertEqual(v["verdict"], "accepted")
        self.assertTrue(all(v[k] for k in ("system_records_in_file", "within_window", "requester_in_capture",
                                           "no_other_reading")))

    def test_requester_missing_from_a_multi_system_capture_is_unmet(self):
        a, st = self.setup([("account_service", {"account_55"}), ("search_service", set())], requester_in_file=False)
        self.assertEqual(self.verdict(a, st)["verdict"], "conditions_unmet:requester_in_capture")

    def test_single_system_snapshot_is_accepted_without_requester_records(self):
        a, st = self.setup([("account_service", {"account_55"})], requester_in_file=False)
        v = self.verdict(a, st)
        self.assertEqual((v["verdict"], v["single_system_snapshot"]), ("accepted_single_system_snapshot", True))

    def test_any_other_reading_of_the_target_is_unmet(self):
        a, st = self.setup([("account_service", {"account_55"}), ("search_service", {"search_95"})],
                           extra=[o("ev_other", "2026-09-01T00:00:00Z", "account_95", "PRESENT", "USER_PROFILE")])
        self.assertEqual(self.verdict(a, st)["verdict"], "conditions_unmet:no_other_reading")

    def test_capture_outside_the_window_is_unmet(self):
        a, st = self.setup([("account_service", {"account_55"}), ("search_service", {"search_95"})],
                           at="2026-08-20T09:00:00Z")
        self.assertIn("within_window", self.verdict(a, st)["verdict"])

    def test_no_records_of_the_system_in_the_file_is_unmet(self):
        a, st = self.setup([("account_service", set()), ("search_service", {"search_95"})])
        self.assertIn("system_records_in_file", self.verdict(a, st)["verdict"])


class PolicyCategoryConflictTests(unittest.TestCase):
    def test_explicit_categories_with_different_treatments_are_reported(self):
        attachment = o("ev_attach", FRESH, "support_901", "PRESENT", "SUPPORT_ATTACHMENT", True)
        attachment.attrs["event"] = "attachment_pii_scan"
        message = o("ev_message", FRESH, "support_901", "PRESENT", "SUPPORT_MESSAGE", True)
        message.attrs["record_type"] = "SUPPORT_MESSAGE"
        a = build_auditor([attachment, message])
        conflicts = policy_category_conflicts(a, {"support_901"}, "2026-09-20T12:00:00Z")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["policy_actions"], {"SUPPORT_ATTACHMENT": ["DELETE"],
                                                           "SUPPORT_MESSAGE": ["REDACT"]})
        self.assertEqual(conflicts[0]["evidence"], {"SUPPORT_ATTACHMENT": ["ev_attach"],
                                                    "SUPPORT_MESSAGE": ["ev_message"]})

    def test_prefix_defaults_and_late_labels_do_not_create_policy_conflicts(self):
        generic = o("ev_generic", FRESH, "support_902", "PRESENT", "SUPPORT_MESSAGE", True)
        late = o("ev_late", "2026-09-21T00:00:00Z", "support_902", "PRESENT", "SUPPORT_ATTACHMENT", True)
        late.attrs["record_type"] = "SUPPORT_ATTACHMENT"
        a = build_auditor([generic, late])
        self.assertEqual(policy_category_conflicts(a, {"support_902"}, "2026-09-20T12:00:00Z"), [])


class RealOmissionPolicyTests(unittest.TestCase):
    """The policy on the real data: evidence_54 (gold) stays accepted; the 33 are accepted; six reviews."""
    SIX = {"case_58", "case_155", "case_157", "case_162", "case_260", "case_462"}
    DECLARED_TWO = {"case_178", "case_547"}          # FAILED claim + omission from a declared-scope snapshot
    CONTESTED_12 = {"case_59", "case_107", "case_155", "case_257", "case_308", "case_362", "case_408", "case_409",
                    "case_411", "case_412", "case_506", "case_512"}

    @classmethod
    def setUpClass(cls):
        cls.orch = af.orchestrator()
        _, cls.auditor, _, cls.cases = af.env()
        cls.cards = {cid: cls.orch.run(c) for cid, c in cls.cases.items()}

    def omissions(self, cid):
        return [x for x in self.cards[cid][1]["step_audit"] if x["state"]["basis"] == "omission"]

    def test_evidence_54_gold_cases_stay_accepted(self):
        for cid, rid in (("case_01", "account_001"), ("case_02", "account_002")):
            d, card = self.cards[cid]
            self.assertEqual(d.status, "COMPLETE", cid)                                  # gold status
            x = [x for x in self.omissions(cid) if x["resource_id"] == rid][0]
            self.assertEqual(x["state"]["policy"]["verdict"], "accepted_single_system_snapshot", cid)
            self.assertEqual(card["decision"]["steps"][x["step_no"] - 1]["evidence_id"], "evidence_54")
            self.assertTrue(card["gates"]["G11_omission_scope"].startswith("flag:"), cid)
            self.assertIn(f"OMISSION_SCOPE_REVIEW:{rid}:inferred:accepted_single_system_snapshot", card["flags"])
            self.assertTrue(card["review"]["required"], cid)

    def test_no_omission_citation_fails_the_policy(self):
        verdicts = {x["state"]["policy"]["verdict"] for cid in self.cards for x in self.omissions(cid)}
        self.assertEqual(verdicts - {"accepted", "accepted_single_system_snapshot", "declared_scope"}, set())

    def test_exactly_the_failed_claim_cases_are_flagged_for_review_not_downgraded(self):
        flagged = {cid for cid, (_, card) in self.cards.items()
                   if any(f.startswith("FAILED_CLAIM_VS_OMISSION:") for f in card["flags"])}
        self.assertEqual(flagged, self.SIX | self.DECLARED_TWO)
        for cid in self.SIX | self.DECLARED_TWO:
            d, card = self.cards[cid]
            engine = self.auditor.audit(self.cases[cid])
            self.assertEqual((d.status, d.steps), (engine.status, engine.steps), cid)      # no automatic change
            self.assertEqual(d.status, "COMPLETE", cid)
            self.assertTrue(card["review"]["required"], cid)
            conflict = [c for c in card["contradictions"] if c["kind"] == "failed_claim_vs_omission"]
            self.assertEqual(len(conflict), 1, cid)
            self.assertEqual(conflict[0]["resolution"], "review_required", cid)
            self.assertTrue(conflict[0]["evidence"][0].startswith("activity_"), cid)

    def test_case_178_declared_scope_conflict(self):
        d, card = self.cards["case_178"]
        c = [c for c in card["contradictions"] if c["kind"] == "failed_claim_vs_omission"]
        self.assertEqual([(x["resource_id"], x["snapshot_scope"], x["resolution"]) for x in c],
                         [("account_1090", "declared", "review_required")])
        self.assertEqual(d.status, "COMPLETE")
        self.assertTrue(card["review"]["required"])
        self.assertNotIn("ACCOUNT_ATTRIBUTION_REVIEW:account_1090", card["flags"])     # inferred, no cross-case tie

    def test_case_547_conflict_and_attribution_review_without_reassignment(self):
        d, card = self.cards["case_547"]
        engine = self.auditor.audit(self.cases["case_547"])
        self.assertEqual((d.status, d.steps), (engine.status, engine.steps))
        self.assertIn(("VERIFY_RECORD_ABSENT", "account_410"), [(s.operation, s.resource_id) for s in d.steps])
        c = [c for c in card["contradictions"] if c["kind"] == "failed_claim_vs_omission"]
        self.assertEqual([(x["resource_id"], x["snapshot_scope"]) for x in c], [("account_410", "declared")])
        self.assertIn("ACCOUNT_ATTRIBUTION_REVIEW:account_410", card["flags"])
        gap = [g for g in card["evidence_gaps"] if g["kind"] == "account_attribution_review"]
        self.assertEqual(gap[0]["rival_of"], ["case_23"])
        self.assertIn("ACCOUNT_ATTRIBUTION_REVIEW:account_410", card["review"]["reasons"])

    def test_attribution_review_applies_to_case_547_only(self):
        hit = {cid for cid, (_, card) in self.cards.items()
               if any(f.startswith("ACCOUNT_ATTRIBUTION_REVIEW:") for f in card["flags"])}
        self.assertEqual(hit, {"case_547"})

    def test_the_twelve_contested_ownership_flags_are_preserved(self):
        for cid in self.CONTESTED_12:
            _, card = self.cards[cid]
            self.assertIn("ACCOUNT_WORKFLOW_TIME_ONLY_TIE", card["flags"], cid)
            self.assertTrue(any(x["ownership"]["tier"] == "contested" for x in self.omissions(cid)), cid)

    def test_case_34_policy_category_conflict_is_review_only(self):
        decision, card = self.cards["case_34"]
        engine = self.auditor.audit(self.cases["case_34"])
        self.assertEqual((decision.status, decision.steps), (engine.status, engine.steps))
        self.assertIn("RECORD_CATEGORY_CONFLICT:support_9538", card["flags"])
        gap = [x for x in card["evidence_gaps"] if x["kind"] == "record_category_conflict"]
        self.assertEqual(gap[0]["policy_actions"], {"SUPPORT_ATTACHMENT": ["DELETE"],
                                                     "SUPPORT_MESSAGE": ["REDACT"]})
        self.assertIn("RECORD_CATEGORY_CONFLICT:support_9538", card["review"]["reasons"])


if __name__ == "__main__":
    unittest.main()

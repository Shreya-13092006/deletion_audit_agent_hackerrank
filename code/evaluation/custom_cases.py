"""Hand-built evaluation cases (synthetic, fictional identities) run through the real pipeline.

Each case supplies its own small evidence store so a single rule is exercised in isolation:
the expected output is written by hand from the policy, not produced by the code.
"""
from __future__ import annotations

import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from audit import config  # noqa: E402
from audit.identity import IdentityGraph, email_hash  # noqa: E402
from audit.parsers.activity import ActivityIndex  # noqa: E402
from audit.parsers import EvidenceStore  # noqa: E402
from audit.pipeline import Auditor  # noqa: E402
from audit.policy import load_rules  # noqa: E402
from audit.schema import Case, Identity, Observation, ScopeCover  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402
from audit import guardrails as g  # noqa: E402

AUDIT = "2026-09-20T12:00:00Z"


def o(ev, at, rid, state, rtype, pii=None, **ids):
    from audit.aliases import system_for
    return Observation(ev, at, at, system_for(rid), rid, rtype, state, pii,
                       emails=set(ids.get("emails", ())), hashes=set(ids.get("hashes", ())),
                       users=set(ids.get("users", ())))


def build_auditor(observations, covers=(), links=(), recreation=()):
    a = Auditor.__new__(Auditor)
    a.trail = AuditTrail(None)
    a.llm = None
    a.parser_cap = g.Capability("parser")
    a.planner_cap = g.Capability("planner")
    ident = Identity("user_900", {"rowan.vale@example.test", "r.vale.old@example.test"},
                     {email_hash("rowan.vale@example.test"), email_hash("r.vale.old@example.test")},
                     {"+00 000 0000"}, {"Rowan Vale"})
    a.graph = IdentityGraph({"user_900": ident})
    activity = ActivityIndex(recreation_links=list(recreation))
    a.store = EvidenceStore(manifest={}, observations=list(observations), covers=list(covers),
                            links=list(links), activity=activity)
    a.rules = load_rules(config.DATASET_DIR)
    a.by_resource = {}
    for ob in a.store.observations:
        a.by_resource.setdefault(ob.resource_id, []).append(ob)
    a.workflow_resources = {}
    a.ambiguous_accounts = {}
    return a


def case(text, email="rowan.vale@example.test"):
    return Case("custom", email, "2026-09-10T12:00:00Z", "COMPLETE", "2026-09-11T12:00:00Z", AUDIT, text)


CUSTOM_CASES = [
    {
        "name": "C1 old-email hash link (historical identifier only)",
        "case": case("Please delete my account and everything tied to my old address too.",
                     email="R.Vale.Old@Example.test "),
        "evidence": dict(observations=[
            o("ev_a", "2026-09-15T10:00:00Z", "account_77", "ABSENT", "USER_PROFILE", emails={"rowan.vale@example.test"}),
            o("ev_a", "2026-09-15T10:05:00Z", "analytics_77", "PRESENT", "MARKETING_PROFILE",
              hashes={email_hash("r.vale.old@example.test")}),
        ]),
        "expected": ("INCOMPLETE", [
            ("FINDING", "analytics_77", "REPORT_REMAINING_RECORD", "ev_a"),
            ("REMEDIATION", "analytics_77", "DELETE_RECORD", ""),
            ("VERIFICATION", "account_77", "VERIFY_RECORD_ABSENT", ""),
            ("VERIFICATION", "analytics_77", "VERIFY_RECORD_ABSENT", ""),
        ]),
    },
    {
        "name": "C2 replica drift: primary deleted, read replica still serves the profile",
        "case": case("Please erase my account."),
        "evidence": dict(observations=[
            o("ev_b", "2026-09-18T09:00:00Z", "account_78", "PRESENT", "USER_PROFILE", True,
              emails={"rowan.vale@example.test"}, users={"user_900"}),
        ], covers=[ScopeCover("ev_b", "2026-09-18T09:00:00Z", "account_service", frozenset({"account_78"}))]),
        "expected": ("INCOMPLETE", [
            ("FINDING", "account_78", "REPORT_REMAINING_RECORD", "ev_b"),
            ("REMEDIATION", "account_78", "DELETE_RECORD", ""),
            ("VERIFICATION", "account_78", "VERIFY_RECORD_ABSENT", ""),
        ]),
    },
    {
        "name": "C3 later evidence must not change the answer at audit_at",
        "case": case("I want my account permanently deleted."),
        "evidence": dict(observations=[
            o("ev_c", "2026-09-19T08:00:00Z", "account_79", "ABSENT", "USER_PROFILE", emails={"rowan.vale@example.test"}),
            o("ev_c", "2026-09-19T08:00:00Z", "audit_record_79", "PRESENT", "SECURITY_AUDIT_LOG", users={"user_900"}),
            o("ev_late", "2026-09-25T08:00:00Z", "search_79", "PRESENT", "SEARCH_INDEX_ENTRY", True,
              emails={"rowan.vale@example.test"}),
        ]),
        "expected": ("COMPLETE", [
            ("VERIFICATION", "account_79", "VERIFY_RECORD_ABSENT", "ev_c"),
            ("VERIFICATION", "audit_record_79", "VERIFY_RECORD_PRESENT", "ev_c"),
        ]),
    },
    {
        "name": "C4 connector repopulates a deleted search entry; backup can restore",
        "case": case("Delete my account and stop anything that copies my data back."),
        "evidence": dict(observations=[
            o("ev_d", "2026-09-18T10:00:00Z", "account_80", "ABSENT", "USER_PROFILE", emails={"rowan.vale@example.test"}),
            o("ev_d", "2026-09-18T10:00:00Z", "search_80", "PRESENT", "SEARCH_INDEX_ENTRY", True,
              emails={"rowan.vale@example.test"}),
            o("ev_d", "2026-09-18T10:00:00Z", "data_flow_80", "ACTIVE", "DATA_FLOW"),
            o("ev_d", "2026-09-18T10:00:00Z", "backup_80", "ACTIVE", "BACKUP_ARCHIVE", users={"user_900"}),
        ], recreation=[("data_flow_80", "search_80", {"event_time": "2026-09-17T00:00:00Z", "activity_id": "activity_x"})]),
        "expected": ("INCOMPLETE", [
            ("FINDING", "search_80", "REPORT_REMAINING_RECORD", "ev_d"),
            ("FINDING", "data_flow_80", "REPORT_ACTIVE_DATA_FLOW", "ev_d"),
            ("FINDING", "backup_80", "REPORT_RESTORE_RISK", "ev_d"),
            ("REMEDIATION", "data_flow_80", "DISABLE_DATA_FLOW", ""),
            ("REMEDIATION", "backup_80", "BLOCK_RESTORE", ""),
            ("REMEDIATION", "search_80", "DELETE_RECORD", ""),
            ("VERIFICATION", "account_80", "VERIFY_RECORD_ABSENT", ""),
            ("VERIFICATION", "search_80", "VERIFY_RECORD_ABSENT", ""),
            ("VERIFICATION", "data_flow_80", "VERIFY_DATA_FLOW_DISABLED", ""),
            ("VERIFICATION", "backup_80", "VERIFY_RESTORE_BLOCKED", ""),
        ]),
    },
    {
        "name": "C6 months-old screenshot reading does not establish state at audit_at",
        "case": case("Please delete my account."),
        "evidence": dict(observations=[
            o("ev_f", "2026-09-19T10:00:00Z", "account_82", "ABSENT", "USER_PROFILE", emails={"rowan.vale@example.test"}),
            o("ev_old", "2026-03-01T10:00:00Z", "export_82", "PRESENT", "USER_EXPORT", True,
              emails={"rowan.vale@example.test"}),
        ]),
        "expected": ("COMPLETE", [
            ("VERIFICATION", "account_82", "VERIFY_RECORD_ABSENT", "ev_f"),
        ]),
    },
    {
        "name": "C5 marketing opt-out containing the word 'remove' is not a deletion",
        "case": case("Please remove me from marketing lists only; keep my account."),
        "evidence": dict(observations=[
            o("ev_e", "2026-09-18T10:00:00Z", "account_81", "PRESENT", "USER_PROFILE", True,
              emails={"rowan.vale@example.test"}),
        ]),
        "expected": ("NOT_APPLICABLE", []),
    },
]


def run_custom_cases() -> int:
    passed = 0
    for spec in CUSTOM_CASES:
        auditor = build_auditor(**spec["evidence"])
        decision = auditor.audit(spec["case"])
        got = (decision.status, [(s.phase, s.resource_id, s.operation, s.evidence_id) for s in decision.steps])
        ok = got == spec["expected"]
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {spec['name']}")
        if not ok:
            print("   expected:", spec["expected"])
            print("   got:     ", got)
    print(f"{passed}/{len(CUSTOM_CASES)} custom cases passed")
    return 0 if passed == len(CUSTOM_CASES) else 1


if __name__ == "__main__":
    raise SystemExit(run_custom_cases())

"""State resolution, policy application and step planning."""
import json
import unittest

from helpers import ScopeCover, obs

from audit import config
from audit.planner import plan, to_json
from audit.policy import Treatment, evaluate, load_rules
from audit.state import resolve

RULES = load_rules(config.DATASET_DIR)
AUDIT = "2026-09-15T12:00:00Z"


class StateTests(unittest.TestCase):
    def test_audit_cutoff_ignores_later_evidence(self):
        rs = resolve("search_1", [obs("search_1", "PRESENT", "2026-09-10T00:00:00Z", "evidence_a"),
                                  obs("search_1", "ABSENT", "2026-09-20T00:00:00Z", "evidence_b")], [], AUDIT)
        self.assertEqual((rs.state, rs.evidence_id), ("PRESENT", "evidence_a"))

    def test_file_captured_after_audit_is_invisible(self):
        late = obs("search_1", "ABSENT", "2026-09-10T00:00:00Z", "evidence_b", captured_at="2026-09-17T00:00:00Z")
        rs = resolve("search_1", [obs("search_1", "PRESENT", "2026-09-01T00:00:00Z", "evidence_a"), late], [], AUDIT)
        self.assertEqual(rs.state, "PRESENT")

    def test_replica_drift_any_copy_present_means_present(self):
        at = "2026-09-14T00:00:00Z"
        rs = resolve("account_994", [obs("account_994", "ABSENT", at, "evidence_05", replica="primary"),
                                     obs("account_994", "PRESENT", at, "evidence_05", replica="read_replica")],
                     [], AUDIT)
        self.assertEqual(rs.state, "PRESENT")

    def test_later_reading_wins_timeline(self):
        rs = resolve("account_8473", [obs("account_8473", "PRESENT", "2026-08-31T07:00:00Z", "evidence_08"),
                                      obs("account_8473", "ABSENT", "2026-09-06T07:00:00Z", "evidence_08")],
                     [], AUDIT)
        self.assertEqual(rs.state, "ABSENT")

    def test_snapshot_scope_absence_only_for_covered_system(self):
        cover = ScopeCover("evidence_54", "2026-09-02T23:00:00Z", "account_service", frozenset({"account_8741"}))
        self.assertEqual(resolve("account_001", [], [cover], AUDIT).state, "ABSENT")
        self.assertEqual(resolve("search_001", [], [cover], AUDIT).state, "UNKNOWN")

    def test_omission_never_overrides_explicit_reading(self):
        cover = ScopeCover("evidence_51", "2026-09-15T12:00:00Z", "security_service", frozenset())
        rs = resolve("audit_record_3737", [obs("audit_record_3737", "PRESENT", "2026-09-15T09:59:00Z", "evidence_92")],
                     [cover], AUDIT)
        self.assertEqual(rs.state, "PRESENT")

    def test_cover_captured_after_audit_ignored(self):
        cover = ScopeCover("evidence_17", "2026-09-20T00:00:00Z", "account_service", frozenset())
        self.assertEqual(resolve("account_1", [], [cover], AUDIT).state, "UNKNOWN")


class PolicyTests(unittest.TestCase):
    def treat(self, rid, state="PRESENT", pii=None, record_type=None):
        o = obs(rid, state, pii=pii, ev="evidence_q")
        if record_type:
            o.record_type = record_type
        return evaluate(resolve(rid, [o], [], AUDIT), RULES)

    def test_security_audit_log_is_retained_not_deleted(self):
        t = self.treat("audit_record_1", "PRESENT")
        self.assertEqual((t.finding, t.remediation, t.verification), (None, None, "VERIFY_RECORD_PRESENT"))

    def test_legal_hold_retained(self):
        self.assertEqual(self.treat("legal_hold_1").verification, "VERIFY_RECORD_PRESENT")

    def test_analytics_with_identifiers_anonymized(self):
        t = self.treat("analytics_1", pii=True)
        self.assertEqual((t.finding, t.remediation), ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD"))

    def test_case12_contact_record_is_deleted_not_anonymized(self):
        t = self.treat("analytics_9914", record_type="MARKETING_PROFILE")
        self.assertEqual((t.finding, t.remediation), ("REPORT_REMAINING_RECORD", "DELETE_RECORD"))

    def test_support_message_redacted_but_attachment_deleted(self):
        self.assertEqual(self.treat("support_1", pii=True).remediation, "REDACT_RECORD")
        self.assertEqual(self.treat("support_2", record_type="SUPPORT_ATTACHMENT").remediation, "DELETE_RECORD")

    def test_tombstone_keeps_reference_redacts_identifiers(self):
        self.assertEqual(self.treat("tombstone_1", pii=True).remediation, "REDACT_RECORD")
        self.assertEqual(self.treat("tombstone_2", pii=False).verification, "VERIFY_RECORD_REDACTED")

    def test_recreation_paths(self):
        flow = self.treat("data_flow_1", "ACTIVE")
        self.assertEqual((flow.finding, flow.remediation), ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW"))
        backup = self.treat("backup_1", "ACTIVE")
        self.assertEqual((backup.finding, backup.remediation), ("REPORT_RESTORE_RISK", "BLOCK_RESTORE"))
        self.assertEqual(self.treat("backup_2", "BLOCKED").verification, "VERIFY_RESTORE_BLOCKED")


class PlannerTests(unittest.TestCase):
    def rs(self, rid, state, pii=None):
        return resolve(rid, [obs(rid, state, pii=pii, ev="evidence_1")], [], AUDIT)

    def test_incomplete_order_and_blank_future_evidence(self):
        items = [(r, evaluate(r, RULES)) for r in (
            self.rs("search_5", "PRESENT"), self.rs("data_flow_2", "ACTIVE"),
            self.rs("audit_record_3", "PRESENT"), self.rs("support_4", "PRESENT", pii=True),
            self.rs("account_1", "ABSENT"))]
        status, steps = plan(items)
        self.assertEqual(status, "INCOMPLETE")
        payload = json.loads(to_json(steps))
        self.assertEqual([s["step_no"] for s in payload], list(range(1, len(payload) + 1)))
        ops = [s["operation"] for s in payload]
        self.assertEqual(ops[:3], ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW"])
        self.assertLess(ops.index("DISABLE_DATA_FLOW"), ops.index("DELETE_RECORD"))
        for s in payload:
            self.assertEqual(bool(s["evidence_id"]), s["phase"] == "FINDING")

    def test_complete_has_only_cited_verification(self):
        items = [(r, evaluate(r, RULES)) for r in (self.rs("account_1", "ABSENT"), self.rs("audit_record_2", "PRESENT"))]
        status, steps = plan(items)
        self.assertEqual(status, "COMPLETE")
        self.assertTrue(all(s.phase == "VERIFICATION" and s.evidence_id for s in steps))

    def test_future_only_check_not_in_complete(self):
        r = self.rs("account_1", "ABSENT")
        items = [(r, evaluate(r, RULES)),
                 (self.rs("audit_record_9", "PRESENT"), Treatment(None, None, "VERIFY_RECORD_PRESENT", "", future_only=True))]
        _, steps = plan(items)
        self.assertEqual([s.resource_id for s in steps], ["account_1"])


if __name__ == "__main__":
    unittest.main()

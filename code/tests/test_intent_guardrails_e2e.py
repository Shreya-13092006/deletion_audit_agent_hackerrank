"""Intent classification, guardrails, and end-to-end checks on the real dataset."""
import csv
import json
import unittest

from helpers import real_auditor

from audit import config
from audit.guardrails import ApprovalGate, Capability, scrub_pii
from audit.intent import classify
from audit.schema import Step


class IntentTests(unittest.TestCase):
    def test_multilingual_deletion(self):
        for text in ["Please erase the account linked to this email address.",
                     "Solicito la eliminación permanente de la cuenta asociada a este correo.",
                     "Je demande la suppression définitive du compte associé à cette adresse e-mail.",
                     "Solicito a exclusão permanente da conta associada a este e-mail.",
                     "このメールアドレスに関連するアカウントの完全な削除を依頼します。",
                     "이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다."]:
            self.assertTrue(classify(text, False)[0], text)

    def test_non_deletion_requests(self):
        for text in ["Please remove me from marketing lists only. I still want receipts.",
                     "Could you send me a copy of the information held on my account?",
                     "My surname is misspelled on the account. Can you correct it without removing any of my records?",
                     "I can't access my profile and need help resetting the login. Do not close the account."]:
            self.assertFalse(classify(text, False)[0], text)

    def test_remove_remaining_copy_is_deletion(self):
        self.assertTrue(classify("Please remove any remaining copy of my profile.", False)[0])

    def test_classify_request_activity_corroborates(self):
        authorized, _, reason = classify("Hello, I have a question about my account.", True)
        self.assertFalse(authorized)
        self.assertEqual(reason, "activity:classify_request")

    def test_undetermined_text_fails_safe(self):
        authorized, flags, _ = classify("Hello there.", False, llm=None)
        self.assertFalse(authorized)
        self.assertIn("INTENT_UNDETERMINED", flags)


class GuardrailTests(unittest.TestCase):
    def test_pii_scrubbed_before_model(self):
        out = scrub_pii("mail a.b@x.com, call +44 20 7946 0958, ref user_12, hash " + "a" * 64)
        for secret in ("a.b@x.com", "7946", "user_12", "a" * 64):
            self.assertNotIn(secret, out)

    def test_rbac_denies_out_of_role(self):
        with self.assertRaises(PermissionError):
            Capability("planner").require("execute_remediation")
        with self.assertRaises(PermissionError):
            Capability("superuser")

    def test_irreversible_operation_needs_approval(self):
        gate = ApprovalGate()
        step = Step("REMEDIATION", "search_service", "search_1", "DELETE_RECORD", "ABSENT")
        with self.assertRaises(PermissionError):
            gate.execute("case_1", step, Capability("executor"))

    def test_ambiguous_identity_fails_safe(self):
        auditor, _ = real_auditor()
        from audit.schema import Case
        unknown = Case("case_x", "nobody@example.invalid", "2026-09-01T00:00:00Z", "COMPLETE",
                       "2026-09-02T00:00:00Z", "2026-09-03T00:00:00Z", "Please delete my account.")
        decision = auditor.audit(unknown)
        self.assertIn("IDENTITY_UNRESOLVED", decision.flags)
        self.assertNotEqual(decision.status, "COMPLETE")


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auditor, cls.cases = real_auditor()
        with open(config.DATASET_DIR / "sample_output.csv", encoding="utf-8", newline="") as fh:
            cls.gold = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}

    def decide(self, cid):
        return self.auditor.audit(self.cases[cid])

    def test_all_three_classifications(self):
        self.assertEqual(self.decide("case_538").status, "NOT_APPLICABLE")   # marketing-only trap
        self.assertEqual(self.decide("case_01").status, "COMPLETE")
        self.assertEqual(self.decide("case_05").status, "INCOMPLETE")

    def test_case12_hash_trap(self):
        steps = {(s.resource_id, s.operation) for s in self.decide("case_12").steps}
        self.assertIn(("analytics_9914", "REPORT_REMAINING_RECORD"), steps)
        self.assertIn(("analytics_9914", "DELETE_RECORD"), steps)

    def test_replica_drift_case16(self):
        steps = {(s.resource_id, s.operation, s.evidence_id) for s in self.decide("case_16").steps}
        self.assertIn(("account_994", "REPORT_REMAINING_RECORD", "evidence_05"), steps)

    def test_decoy_search_not_attributed_case28(self):
        self.assertFalse(any(s.system_id == "search_service" for s in self.decide("case_28").steps))

    def test_tombstone_cases(self):
        self.assertEqual(self.decide("case_31").status, "COMPLETE")
        ops = {(s.resource_id, s.operation) for s in self.decide("case_32").steps}
        self.assertIn(("tombstone_9178", "REDACT_RECORD"), ops)

    def test_sample_status_accuracy_floor(self):
        hits = sum(self.decide(cid).status == g[0] for cid, g in self.gold.items())
        self.assertGreaterEqual(hits / len(self.gold), 0.95)

    def test_no_citation_after_audit(self):
        manifest = self.auditor.store.manifest
        for cid, case in self.cases.items():
            for s in self.decide(cid).steps:
                if s.evidence_id in manifest:
                    self.assertLessEqual(manifest[s.evidence_id]["captured_at"], case.audit_at, cid)


if __name__ == "__main__":
    unittest.main()

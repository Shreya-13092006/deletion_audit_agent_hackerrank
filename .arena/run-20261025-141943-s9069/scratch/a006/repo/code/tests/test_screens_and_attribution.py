"""Screenshot extraction (pydantic schema, closed-world OCR parsing), freshness horizon and
workflow attribution."""
import json
import unittest

from helpers import obs, real_auditor

from pydantic import ValidationError

from audit import config
from audit.screen_ocr import parse_screen
from audit.state import resolve
from audit.vision_schema import ExtractedRecord, ImageFacts, ImageFactsCache


def ocr(*rows, scale=1):
    """Fake OCR output: rows of (text, y) at the given scale."""
    return {"lines": [{"text": t, "words": [{"text": t, "x": 10 * scale, "y": y * scale, "w": 50, "h": 10 * scale}]}
                      for t, y in rows]}


KNOWN = dict(known_resources={"backup_9287", "audit_record_003"}, known_emails={"areed1433@gmail.com"},
             known_users={"user_03", "user_16"}, reference_index={})


class SchemaTests(unittest.TestCase):
    def test_valid_record(self):
        rec = ExtractedRecord(resource_id="backup_9287", record_type="BACKUP_ARCHIVE", result="ACTIVE",
                              email="areed1433@gmail.com", restore_allowed=True)
        self.assertEqual(rec.resource_id, "backup_9287")

    def test_rejects_malformed_identifiers_and_unknown_fields(self):
        for bad in ({"resource_id": "backup_92gI"}, {"resource_id": "backup_1", "email": "not-an-email"},
                    {"resource_id": "backup_1", "customer_reference": "user_ll"},
                    {"resource_id": "backup_1", "result": "MAYBE"}, {"resource_id": "backup_1", "extra": 1}):
            with self.assertRaises(ValidationError):
                ExtractedRecord(**bad)

    def test_shipped_cache_validates(self):
        data = json.loads((config.CACHE_DIR / "image_facts.json").read_text(encoding="utf-8"))
        ImageFactsCache.model_validate(data)
        self.assertEqual(len(data), 11)
        for entry in data.values():
            ImageFacts.model_validate(entry)


class ScreenParsingTests(unittest.TestCase):
    def test_confusion_repair_only_to_known_identifiers(self):
        screen = {"1": ocr(("backup_92B7 areed1433@gmaiI.com", 100)),
                  "2": ocr(("backup_9287 areed1433@gmail.com", 100), scale=2)}
        records, rejected, _ = parse_screen(screen, **KNOWN)
        self.assertEqual([r["resource_id"] for r in records], ["backup_9287"])
        self.assertEqual(records[0]["email"], "areed1433@gmail.com")
        self.assertTrue(records[0]["restore_allowed"])

    def test_unknown_identifier_needs_two_agreeing_readings(self):
        one = {"1": ocr(("backup_9291", 50)), "2": ocr(("backup_9297", 50), scale=2)}
        records, rejected, _ = parse_screen(one, **KNOWN)
        self.assertEqual(records, [])
        self.assertIn("backup_9291", rejected)
        two = {"1": ocr(("backup_92gI", 50)), "2": ocr(("backup_9291", 50), scale=2)}
        records, _, _ = parse_screen(two, **KNOWN)
        self.assertEqual([r["resource_id"] for r in records], ["backup_9291"])

    def test_decoy_row_contact_not_attached_to_subject(self):
        screen = {"2": ocr(("Subject filter: user_03", 20), ("audit_record_003", 100),
                           ("backup_9287 someone@else.com", 200), scale=2),
                  "1": ocr(("audit_record_003", 100), ("backup_9287", 200))}
        records = {r["resource_id"]: r for r in parse_screen(screen, **KNOWN)[0]}
        self.assertEqual(records["audit_record_003"].get("customer_reference"), "user_03")
        self.assertNotIn("customer_reference", records["backup_9287"])
        self.assertIn("someone@else.com", records["backup_9287"]["note"])


class FreshnessTests(unittest.TestCase):
    def test_stale_reading_does_not_establish_state(self):
        old = obs("tombstone_17", "PRESENT", "2026-03-10T06:00:00Z", "evidence_42")
        self.assertEqual(resolve("tombstone_17", [old], [], "2026-09-15T12:00:00Z", 14).state, "UNKNOWN")
        self.assertEqual(resolve("tombstone_17", [old], [], "2026-03-11T08:00:00Z", 14).state, "PRESENT")


class AttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auditor, cls.cases = real_auditor()

    def test_cooccurrence_breaks_same_slot_tie(self):
        steps = {(s.resource_id, s.operation) for s in self.auditor.audit(self.cases["case_28"]).steps}
        self.assertIn(("account_5482", "VERIFY_RECORD_ABSENT"), steps)
        steps = {(s.resource_id, s.operation) for s in self.auditor.audit(self.cases["case_29"]).steps}
        self.assertIn(("account_7012", "VERIFY_RECORD_ABSENT"), steps)

    def test_no_second_record_of_an_identified_system(self):
        steps = {s.resource_id for s in self.auditor.audit(self.cases["case_11"]).steps}
        self.assertNotIn("analytics_9447", steps)

    def test_time_only_tie_is_flagged(self):
        self.assertIn("ACCOUNT_WORKFLOW_TIME_ONLY_TIE", self.auditor.audit(self.cases["case_23"]).flags)

    def test_screenshot_finding_cited(self):
        steps = {(s.resource_id, s.operation, s.evidence_id) for s in self.auditor.audit(self.cases["case_55"]).steps}
        self.assertIn(("backup_9287", "REPORT_RESTORE_RISK", "evidence_32"), steps)


if __name__ == "__main__":
    unittest.main()

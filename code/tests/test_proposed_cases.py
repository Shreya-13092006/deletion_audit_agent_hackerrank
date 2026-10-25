"""Proposed cases P1-P8 from docs/reviews/evaluation-2026-10-25.md §4, adopted as regression tests.

Fictional identity (user_900 / rowan.vale@example.test, old email r.vale.old@example.test) from
evaluation/custom_cases.py; expected results are derived by hand from the dataset rules.
"""
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts code/ on sys.path)
from helpers import email_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
from custom_cases import AUDIT, build_auditor, case, o  # noqa: E402

from audit import guardrails as g  # noqa: E402
from audit.intent import classify  # noqa: E402
from audit.screen_ocr import parse_screen  # noqa: E402
from test_screens_and_attribution import KNOWN, ocr  # noqa: E402

ME = {"emails": {"rowan.vale@example.test"}}
FRESH = "2026-09-19T10:00:00Z"
DELETE = "Please delete my account and all my data."


def ops(decision):
    return [(s.operation, s.resource_id, s.evidence_id) for s in decision.steps]


class ProposedCaseTests(unittest.TestCase):
    def test_p1_historical_email_with_caps_and_spaces_links_hash_only_record(self):
        a = build_auditor([
            o("ev_p1", FRESH, "account_201", "ABSENT", "USER_PROFILE", **ME),
            o("ev_p1", FRESH, "analytics_201", "PRESENT", "ANALYTICS_PROFILE", True,
              hashes={email_hash("r.vale.old@example.test")}),
        ])
        d = a.audit(case(DELETE, email="  R.Vale.OLD@Example.TEST "))
        self.assertEqual(d.status, "INCOMPLETE")
        self.assertEqual(ops(d), [("REPORT_EXPOSED_PII", "analytics_201", "ev_p1"),
                                  ("ANONYMIZE_RECORD", "analytics_201", ""),
                                  ("VERIFY_RECORD_ABSENT", "account_201", ""),
                                  ("VERIFY_RECORD_ANONYMIZED", "analytics_201", "")])

    def test_p2_evidence_exactly_at_audit_counts_one_second_later_does_not(self):
        late = "2026-09-20T12:00:01Z"                  # AUDIT + 1 s
        a = build_auditor([
            o("ev_acct", FRESH, "account_202", "ABSENT", "USER_PROFILE", **ME),
            o("ev_at", AUDIT, "search_202", "PRESENT", "SEARCH_INDEX_ENTRY", True, **ME),
            o("ev_late", late, "search_202", "ABSENT", "SEARCH_INDEX_ENTRY", **ME),
        ])
        d = a.audit(case(DELETE))
        self.assertEqual(d.status, "INCOMPLETE")
        self.assertIn(("REPORT_REMAINING_RECORD", "search_202", "ev_at"), ops(d))
        self.assertNotIn("ev_late", {s.evidence_id for s in d.steps})

    def test_p3_same_name_different_user_is_a_decoy(self):
        decoy = o("ev_d", FRESH, "search_203", "PRESENT", "SEARCH_INDEX_ENTRY", True, users={"user_999"})
        decoy.attrs["display_name"] = "Rowan Vale"                       # same name as the requester
        a = build_auditor([o("ev_d", FRESH, "account_203", "ABSENT", "USER_PROFILE", **ME), decoy])
        d = a.audit(case(DELETE))
        self.assertNotIn("search_203", {s.resource_id for s in d.steps})

    def test_p4_classify_request_contradicting_the_text_does_not_override_it(self):
        authorized, flags, reason = classify("Bitte löschen Sie mein Konto und alle meine Daten.", True)
        self.assertTrue(authorized)
        self.assertIn(g.FLAG_INTENT_CONFLICT, flags)
        self.assertEqual(reason, "rule:deletion")

    def test_p5_marketing_only_opt_out_in_other_languages_is_not_a_deletion(self):
        for text in ("Por favor, elimínenme solo de las listas de marketing.",
                     "Por favor, removam-me apenas das listas de marketing.",
                     "Merci de me supprimer uniquement de la liste marketing."):
            authorized, _, reason = classify(text, False)
            self.assertFalse(authorized, text)
            self.assertEqual(reason, "rule:non_deletion", text)
        # a real deletion that merely mentions marketing, or says "not only marketing", is still a deletion
        self.assertTrue(classify("Eliminen mi cuenta y también mis datos de marketing.", False)[0])
        self.assertTrue(classify("Supprimez mon compte, pas seulement les données marketing.", False)[0])
        self.assertTrue(classify("Please remove me from marketing lists only", False)[0] is False)

    def test_marketing_only_negation_and_mixed_deletion_requests(self):
        # A marketing-only request is a non-deletion even when it explicitly negates deletion.
        non_deletion = (
            "Only remove me from the marketing list.",
            "I do not want to delete my account.",
            "I am not asking for deletion; only remove me from the marketing list.",
            "This is not a request to erase my account.",
            "I do not want to delete my account; only remove me from the marketing list.",
            "No quiero eliminar mi cuenta.",
            "No quiero eliminar mi cuenta; solo quítenme de la lista de marketing.",
            "Não quero excluir minha conta.",
            "Não quero excluir minha conta; removam-me apenas da lista de marketing.",
            "Je ne veux pas supprimer mon compte.",
            "Je ne veux pas supprimer mon compte; retirez-moi uniquement de la liste marketing.",
            "Ich möchte mein Konto nicht löschen.",
        )
        for text in non_deletion:
            with self.subTest(text=text):
                authorized, _, reason = classify(text, False)
                self.assertFalse(authorized)
                self.assertIn(reason, ("rule:non_deletion", "rule:negated_deletion"))

        # An independent account/data deletion still authorizes deletion when marketing opt-out
        # is also requested; the word "only" scopes the marketing action, not the whole request.
        mixed = (
            "Please delete my account and all my data; only remove me from the marketing list as well.",
            "Eliminen mi cuenta y mis datos; además, quítenme únicamente de la lista de marketing.",
            "Eliminem minha conta e meus dados; removam-me também apenas da lista de marketing.",
            "Supprimez mon compte et mes données; retirez-moi aussi uniquement de la liste marketing.",
        )
        for text in mixed:
            with self.subTest(text=text):
                self.assertTrue(classify(text, False)[0], text)

    def test_p6_single_misread_maps_only_to_a_known_identifier(self):
        known = {"1": ocr(("backup_92B7", 100))}                         # one reading, one confusion
        self.assertEqual([r["resource_id"] for r in parse_screen(known, **KNOWN)[0]], ["backup_9287"])
        unknown = {"1": ocr(("backup_93B7", 100))}                       # repairs to an unknown id
        records, rejected, _ = parse_screen(unknown, **KNOWN)
        self.assertEqual(records, [])
        self.assertTrue(any("9387" in r or "93B7" in r for r in rejected))

    def test_p7_retained_order_loaded_trace_gives_a_retained_legal_hold_check(self):
        from audit.parsers.logs import parse_log
        lines = [
            '2026-09-19T09:59:56Z | DEBUG | legal_service | tr-9000001 | retained_order_query_started | subject_ref="user_900"',
            '2026-09-19T10:00:01Z | INFO | legal_service | tr-9000001 | retained_order_loaded | resource_id="legal_hold_90" access="allowed"',
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "legal.log"
            p.write_text("\n".join(lines), encoding="utf-8")
            observations, _ = parse_log(p, "ev_legal", "2026-09-19T12:00:00Z")
        a = build_auditor([o("ev_acct", FRESH, "account_207", "ABSENT", "USER_PROFILE", **ME)] + observations)
        d = a.audit(case(DELETE))
        self.assertEqual(d.status, "COMPLETE")
        self.assertIn(("VERIFY_RECORD_PRESENT", "legal_hold_90", "ev_legal"), ops(d))
        self.assertNotIn("DELETE_RECORD", [s.operation for s in d.steps])

    def test_p8_reading_older_than_the_freshness_horizon_is_not_proof(self):
        a = build_auditor([o("ev_old", "2026-08-31T10:00:00Z", "account_208", "ABSENT", "USER_PROFILE", **ME)])
        d = a.audit(case(DELETE))                                        # 20 days before AUDIT
        self.assertEqual(d.status, "INCOMPLETE")
        self.assertEqual(ops(d), [("VERIFY_RECORD_ABSENT", "account_208", "")])
        self.assertIn(g.FLAG_NO_PROOF, d.flags)


if __name__ == "__main__":
    unittest.main()

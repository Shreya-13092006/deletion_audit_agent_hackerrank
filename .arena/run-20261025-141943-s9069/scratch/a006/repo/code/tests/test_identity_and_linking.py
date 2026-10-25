"""Identity resolution, alias map and linking rules."""
import unittest

from helpers import FakeStore, email_hash, ident, obs, real_auditor, real_graph

from audit.aliases import classify_value, extract_identifiers, record_type_for, system_for
from audit.linker import link_resources, matches


class IdentityGraphTests(unittest.TestCase):
    def test_email_casing_and_whitespace(self):
        g = real_graph()
        self.assertEqual(g.resolve_email("  AMINA.ELMASRI@GMAIL.COM "), ["user_01"])

    def test_old_and_new_email_resolve_to_same_user(self):
        g = real_graph()
        # user_12 changed minjun.kim90@gmail.com -> minjun.kim@gmail.com (user_audit_log)
        self.assertEqual(g.resolve_email("minjun.kim90@gmail.com"), ["user_12"])
        self.assertEqual(g.resolve_email("minjun.kim@gmail.com"), ["user_12"])

    def test_hash_algorithm_matches_dataset(self):
        g = real_graph()
        ident12 = g.identities["user_12"]
        # current snapshot hash and sha256(old email) both belong to the user (case_12 trap)
        self.assertIn(email_hash("minjun.kim90@gmail.com"), ident12.hashes)
        self.assertIn("44a65154bfd8e408852578fbd76813d094d1944f255ac1769ee81ba90492f10e", ident12.hashes)

    def test_audit_log_email_hash_rows_are_identifiers(self):
        g = real_graph()
        users_with_hash_history = [u for u in g.identities.values() if len(u.hashes) > 1]
        self.assertGreaterEqual(len(users_with_hash_history), 100)

    def test_unknown_email_does_not_resolve(self):
        self.assertEqual(real_graph().resolve_email("nobody@example.invalid"), [])


class AliasTests(unittest.TestCase):
    def test_alias_fields(self):
        ids = extract_identifiers({"subject_reference": "user_7", "lookup_key": "A@B.COM",
                                   "correlation_key": "AB" * 32, "subject_selector": "user_8",
                                   "requester_email": None, "owner_phone": "+1 555 0100"})
        self.assertEqual(ids["users"], {"user_7", "user_8"})
        self.assertEqual(ids["emails"], {"a@b.com"})
        self.assertEqual(ids["hashes"], {"ab" * 32})
        self.assertEqual(ids["phones"], {"+1 555 0100"})

    def test_lookup_key_user_reference(self):
        self.assertEqual(classify_value("user_49"), ("user", "user_49"))

    def test_prefix_systems(self):
        self.assertEqual(system_for("data_flow_9522"), "integration_service")
        self.assertEqual(system_for("audit_record_3737"), "security_service")
        self.assertEqual(system_for("tombstone_440"), "identity_service")
        self.assertEqual(record_type_for("support_1", "ticket_attachments"), "SUPPORT_ATTACHMENT")


class LinkingTests(unittest.TestCase):
    def test_never_link_by_name(self):
        me = ident(emails=("jonas.berg@outlook.com",))
        decoy = obs("search_8814", emails={"jonas.berglund@outlook.com"}, attrs={"display_name": "Jonas Berg"})
        self.assertFalse(matches(decoy, me))

    def test_record_naming_other_user_is_not_linked(self):
        me = ident(emails=("a@x.com",))
        other = obs("support_1", emails={"a@x.com"}, users={"user_999"})
        self.assertFalse(matches(other, me))

    def test_hash_only_link(self):
        me = ident(emails=("old@x.com",))
        hashed = obs("analytics_9914", hashes={email_hash("old@x.com")})
        self.assertTrue(matches(hashed, me))

    def test_search_source_resource_links_account(self):
        me = ident(emails=("a@x.com",))
        store = FakeStore([obs("search_1", emails={"a@x.com"}), obs("account_6", state="ABSENT")],
                          links=[("search_1", "account_6", "evidence_57")])
        linked, _ = link_resources(me, store, "2026-12-01T00:00:00Z", {})
        self.assertEqual(linked, {"search_1", "account_6"})

    def test_recreating_connector_is_linked(self):
        me = ident(emails=("a@x.com",))
        store = FakeStore([obs("search_2", emails={"a@x.com"})],
                          recreation=[("data_flow_5", "search_2",
                                       {"event_time": "2026-08-01T00:00:00Z", "activity_id": "activity_1"})])
        linked, _ = link_resources(me, store, "2026-09-01T00:00:00Z", {})
        self.assertIn("data_flow_5", linked)


    def test_phone_alone_never_links_a_record(self):
        from audit.schema import Identity
        me = Identity("user_1", {"a@x.com"}, {email_hash("a@x.com")}, {"+44 20 7946 0958"}, set())
        phone_only = obs("support_7", phones={"+44 20 7946 0958"})
        self.assertFalse(matches(phone_only, me))
        linked, _ = link_resources(me, FakeStore([phone_only]), "2026-09-15T00:00:00Z", {"support_7": [phone_only]})
        self.assertEqual(linked, set())

    def test_phone_is_kept_as_an_identifier_for_provenance(self):
        ids = extract_identifiers({"phone": "+44 20 7946 0958", "email": "A@X.com"})
        self.assertEqual((ids["phones"], ids["emails"]), ({"+44 20 7946 0958"}, {"a@x.com"}))


class TraceJoinTests(unittest.TestCase):
    def test_lookup_errors_and_malformed_counts_do_not_prove_absence(self):
        from audit.parsers.logs import _event_state
        base = {"event": "profile_lookup_completed"}
        self.assertIsNone(_event_state({**base, "http_status": "503"}))
        self.assertIsNone(_event_state({**base, "rows": "not-a-count", "http_status": "503"}))
        self.assertIsNone(_event_state({**base, "rows": "0", "http_status": "503"}))
        self.assertEqual(_event_state({**base, "http_status": "404"})[0], "ABSENT")
        self.assertEqual(_event_state({**base, "http_status": "200"})[0], "PRESENT")

    def test_lookup_counts_are_normalized_before_determining_presence(self):
        from audit.parsers.logs import _event_state
        base = {"event": "profile_lookup_completed"}
        for zero in (0, "0", "00", " 0 "):
            with self.subTest(rows=zero):
                self.assertEqual(_event_state({**base, "rows": zero, "http_status": "200"})[0], "ABSENT")
        for positive in (1, "1", " 12 "):
            with self.subTest(rows=positive):
                self.assertEqual(_event_state({**base, "rows": positive, "http_status": "404"})[0], "PRESENT")

    def test_started_and_completed_lines_joined_by_trace(self):
        import tempfile
        from pathlib import Path
        from audit.parsers.logs import parse_log
        lines = [
            '2026-09-15T11:51:09Z level=DEBUG service=account_service trace_id=tr-1 event=profile_lookup_started lookup_key="leonie@x.com"',
            "2026-09-15T11:51:10Z level=DEBUG service=dns_cache event=cache_refresh entries=3",
            "2026-09-15T11:51:19Z level=INFO service=account_service trace_id=tr-1 resource_id=account_4092 event=profile_lookup_completed rows=0 http_status=404",
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.log"
            p.write_text("\n".join(lines), encoding="utf-8")
            out, _ = parse_log(p, "evidence_t", "2026-09-15T12:00:00Z")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].resource_id, "account_4092")
        self.assertEqual(out[0].state, "ABSENT")
        self.assertEqual(out[0].emails, {"leonie@x.com"})

    def test_retained_order_loaded_is_a_legal_hold_reading_for_the_trace_subject(self):
        # Pattern of operations_stream_eu_central_20260705.log, trace tr-2637487 (pipe format).
        import tempfile
        from pathlib import Path
        from audit.parsers.logs import parse_log
        lines = [
            '2026-07-03T07:56:56Z | DEBUG | legal_service | tr-2637487 | retained_order_query_started | instance="legal-3" subject_ref="user_218" attempt="1"',
            '2026-07-03T07:56:59Z | DEBUG | legal_service | tr-2637487 | connection_acquired | instance="legal-3" pool="legal_service_primary" wait_ms="6"',
            '2026-07-03T07:57:01Z | INFO | legal_service | tr-2637487 | retained_order_loaded | instance="legal-3" resource_id="legal_hold_4961" reason="payment_dispute_and_tax_record" access="allowed"',
            # same event in another trace with no subject: a reading, but tied to nobody
            '2026-07-03T08:01:00Z | INFO | legal_service | tr-9999999 | retained_order_loaded | instance="legal-1" resource_id="legal_hold_7000" access="allowed"',
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ops.log"
            p.write_text("\n".join(lines), encoding="utf-8")
            out, _ = parse_log(p, "evidence_t", "2026-07-05T07:54:00Z")
        by = {o.resource_id: o for o in out}
        self.assertEqual(sorted(by), ["legal_hold_4961", "legal_hold_7000"])
        o = by["legal_hold_4961"]
        self.assertEqual((o.state, o.record_type, o.system_id), ("PRESENT", "LEGAL_HOLD_RECORD", "legal_service"))
        self.assertEqual((o.observed_at, o.captured_at), ("2026-07-03T07:57:01Z", "2026-07-05T07:54:00Z"))
        self.assertEqual(o.source, "log:ops.log:retained_order_loaded")
        self.assertEqual((o.attrs["trace_id"], o.attrs["subject_ref"]), ("tr-2637487", "user_218"))
        self.assertEqual((o.users, o.emails, o.hashes), ({"user_218"}, set(), set()))   # only the trace's subject
        orphan = by["legal_hold_7000"]
        self.assertEqual((orphan.users, orphan.emails, orphan.hashes), (set(), set(), set()))

    def test_legal_hold_4961_links_only_to_user_218(self):
        from audit.linker import link_by_identifier
        auditor, cases = real_auditor()
        owners = set()
        for cid, case in cases.items():
            ident, _ = auditor.identity_for(case)
            if "legal_hold_4961" in link_by_identifier(ident, auditor.store, case.audit_at):
                owners.add((cid, ident.user_id))
        self.assertEqual(owners, {("case_220", "user_218")})
        reading = [o for o in auditor.by_resource["legal_hold_4961"] if o.state != "LINK"
                   and o.source.endswith(":retained_order_loaded")]
        self.assertEqual([(o.evidence_id, o.state, o.users) for o in reading],
                         [("evidence_21", "PRESENT", {"user_218"})])

    def test_all_line_formats_parse(self):
        from audit.parsers.logs import parse_line
        samples = [
            '2026-07-28T05:51:21Z [INFO] [account_service] [tr-6] profile_lookup_completed: resource_id="account_7947" rows="0"',
            '2026-02-03T05:59:27Z | WARN | support_platform | tr-7 | attachment_pii_scan | resource_id="support_4533" matched_value="k@x.com"',
            '2026-08-22T10:51:17Z <15>1 node-1 account_service tr-4 - - level=DEBUG resource_id="account_1785" event="profile_lookup_completed" rows="1"',
            '2026-06-08T09:52:44Z requestId=tr-4 level=WARN function=analytics_platform message="resource_id=\\"analytics_515\\" event=\\"analytics_identity_scan\\""',
            '2026-09-10T08:56:20Z {"service":"account_service","trace_id":"tr-5","resource_id":"account_6633","event":"profile_lookup_completed"}',
        ]
        for line in samples:
            ev = parse_line(line)
            self.assertTrue(ev and ev.get("resource_id") and ev.get("event"), line)


if __name__ == "__main__":
    unittest.main()

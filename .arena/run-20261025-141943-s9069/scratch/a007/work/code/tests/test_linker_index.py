"""The identifier-indexed linker and the Auditor memo must equal the original full scan exactly."""
import unittest

from helpers import FakeStore, ident, obs, real_auditor

from audit.linker import _no_conflict, link_resources, matches, visible


def reference_link_resources(ident_, store, audit_at, by_resource):
    """The original full-scan algorithm, kept verbatim as the oracle."""
    linked = {}
    for o in sorted(store.observations, key=lambda o: not visible(o, audit_at)):
        if matches(o, ident_) and o.resource_id not in linked:
            reason = "identifier" if visible(o, audit_at) else "identifier_later_evidence"
            linked[o.resource_id] = (o.resource_id, reason, o.evidence_id)
    changed = True
    while changed:
        changed = False
        for a, b, ev in store.links:
            if ev in store.manifest and store.manifest[ev]["captured_at"] > audit_at:
                continue
            for x, y in ((a, b), (b, a)):
                if x in linked and y not in linked and _no_conflict(y, ident_, by_resource, audit_at):
                    linked[y] = (y, f"resource_link:{x}", ev)
                    changed = True
        for source, downstream, row in store.activity.recreation_links:
            if row["event_time"] <= audit_at and downstream in linked and source not in linked:
                linked[source] = (source, f"repopulates:{downstream}", row["activity_id"])
                changed = True
    return set(linked), list(linked.values())


class IndexedLinkerEquivalenceTests(unittest.TestCase):
    def test_identical_to_full_scan_for_every_eval_and_sample_case(self):
        auditor, cases = real_auditor()
        self.assertGreaterEqual(len(cases), 550)
        for cid, case in sorted(cases.items()):
            me, _ = auditor.identity_for(case)
            want = reference_link_resources(me, auditor.store, case.audit_at, auditor.by_resource)
            got = link_resources(me, auditor.store, case.audit_at, auditor.by_resource)
            self.assertEqual(got, want, cid)              # provenance order included
            self.assertEqual(auditor.links_for(me, case.audit_at), want, cid)

    def test_visible_evidence_wins_provenance_over_earlier_later_evidence(self):
        me = ident(emails=("a@x.com",))
        late = obs("search_1", ev="ev_late", at="2026-10-01T00:00:00Z", emails={"a@x.com"})
        early = obs("search_1", ev="ev_early", at="2026-08-01T00:00:00Z", emails={"a@x.com"})
        only_late = obs("export_1", ev="ev_late2", at="2026-10-02T00:00:00Z", users={"user_1"})
        decoy = obs("support_9", emails={"a@x.com"}, users={"user_999"})
        store = FakeStore([late, only_late, decoy, early])
        got = link_resources(me, store, "2026-09-01T00:00:00Z", {})
        self.assertEqual(got, reference_link_resources(me, store, "2026-09-01T00:00:00Z", {}))
        self.assertEqual(got[1], [("search_1", "identifier", "ev_early"),
                                  ("export_1", "identifier_later_evidence", "ev_late2")])

    def test_index_rebuilds_when_observations_grow(self):
        me = ident(emails=("a@x.com",))
        store = FakeStore([obs("search_1", emails={"a@x.com"})])
        self.assertEqual(link_resources(me, store, "2026-12-01T00:00:00Z", {})[0], {"search_1"})
        store.observations.append(obs("analytics_2", emails={"a@x.com"}))
        self.assertEqual(link_resources(me, store, "2026-12-01T00:00:00Z", {})[0],
                         {"search_1", "analytics_2"})

    def test_memo_returns_independent_copies(self):
        auditor, cases = real_auditor()
        case = cases[sorted(cases)[0]]
        me, _ = auditor.identity_for(case)
        first, prov = auditor.links_for(me, case.audit_at)
        first.add("mutated_by_caller")
        prov.append(("x", "y", "z"))
        again, prov2 = auditor.links_for(me, case.audit_at)
        self.assertNotIn("mutated_by_caller", again)
        self.assertNotIn(("x", "y", "z"), prov2)


if __name__ == "__main__":
    unittest.main()

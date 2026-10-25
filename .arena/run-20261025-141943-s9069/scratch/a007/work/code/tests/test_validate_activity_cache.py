"""validate_rows builds the activity_id -> event_time map once per activity index (perf B1).

Proves (1) results are identical to the original per-call implementation and (2) the map is
not rebuilt on every call, while a replaced or resized row list still invalidates it.
"""
from __future__ import annotations

import json
import unittest

import helpers  # noqa: F401  (puts code/ on sys.path)
from audit import config
from audit.parsers.activity import ActivityIndex, load_activity
from audit.schema import Case
from audit.validate import activity_time_map, validate_rows


class CountingRows(list):
    """A list that counts full iterations, i.e. map rebuilds."""
    iterations = 0

    def __iter__(self):
        type(self).iterations += 1
        return super().__iter__()


def reference_validate(rows, cases, manifest, activity):
    """Original pre-fix lookup semantics: map rebuilt on each call (evidence checks only)."""
    audit_at = {c.case_id: c.audit_at for c in cases}
    activity_time = {r["activity_id"]: r["event_time"] for r in activity.rows} if activity else {}
    out = []
    for r in rows:
        for i, s in enumerate(json.loads(r["steps_json"]), start=1):
            ev = s["evidence_id"]
            if ev:
                when = manifest.get(ev, {}).get("captured_at") or activity_time.get(ev)
                if when is None:
                    out.append(f"{r['case_id']}: step {i} unknown evidence {ev}")
                elif when > audit_at[r["case_id"]]:
                    out.append(f"{r['case_id']}: step {i} cites {ev} captured after audit_at")
    return out


def case(cid, audit_at):
    return Case(cid, "a@x.com", "2026-01-01T00:00:00Z", "COMPLETE", "2026-01-02T00:00:00Z",
                audit_at, "please delete my account")


def complete_row(cid, ev):
    step = {"step_no": 1, "phase": "VERIFICATION", "system_id": "account_service",
            "resource_id": "account_1", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT",
            "evidence_id": ev}
    return {"case_id": cid, "deletion_status": "COMPLETE", "steps_json": json.dumps([step])}


ACT_ROWS = [{"activity_id": "act_1", "event_time": "2026-03-01T00:00:00Z"},
            {"activity_id": "act_2", "event_time": "2026-05-01T00:00:00Z"}]
MANIFEST = {"evidence_01": {"captured_at": "2026-02-01T00:00:00Z"}}
SCENARIOS = [("c1", "act_1"), ("c2", "act_2"), ("c3", "evidence_01"), ("c4", "act_missing")]


class ValidateActivityCacheTests(unittest.TestCase):
    def run_all(self, activity):
        results = []
        for cid, ev in SCENARIOS:
            rows, cases = [complete_row(cid, ev)], [case(cid, "2026-04-01T00:00:00Z")]
            got = validate_rows(rows, cases, MANIFEST, activity)
            self.assertEqual(got, reference_validate(rows, cases, MANIFEST, activity))
            results.append(got)
        return results

    def test_results_identical_to_per_call_build(self):
        idx = ActivityIndex(rows=[dict(r) for r in ACT_ROWS])
        res = self.run_all(idx)
        self.assertEqual(res[0], [])                                   # in-time activity
        self.assertEqual(res[1], ["c2: step 1 cites act_2 captured after audit_at"])
        self.assertEqual(res[2], [])                                   # manifest evidence
        self.assertEqual(res[3], ["c4: step 1 unknown evidence act_missing"])
        self.assertEqual(self.run_all(None)[0], ["c1: step 1 unknown evidence act_1"])

    def test_map_built_once_per_index(self):
        CountingRows.iterations = 0
        idx = ActivityIndex(rows=CountingRows(dict(r) for r in ACT_ROWS))
        CountingRows.iterations = 0
        for _ in range(50):
            validate_rows([complete_row("c1", "act_1")], [case("c1", "2026-04-01T00:00:00Z")],
                          MANIFEST, idx)
        self.assertEqual(CountingRows.iterations, 1)

    def test_replaced_or_resized_rows_invalidate_cache(self):
        idx = ActivityIndex(rows=[dict(ACT_ROWS[0])])
        self.assertNotIn("act_2", activity_time_map(idx))
        idx.rows.append(dict(ACT_ROWS[1]))                              # resized in place
        self.assertIn("act_2", activity_time_map(idx))
        idx.rows = [{"activity_id": "act_9", "event_time": "2026-01-01T00:00:00Z"}]
        self.assertEqual(activity_time_map(idx), {"act_9": "2026-01-01T00:00:00Z"})

    def test_objects_without_attribute_support_still_work(self):
        class Slotted:
            __slots__ = ("rows",)

            def __init__(self, rows):
                self.rows = rows
        obj = Slotted([dict(r) for r in ACT_ROWS])
        self.assertEqual(activity_time_map(obj), {r["activity_id"]: r["event_time"] for r in ACT_ROWS})
        self.run_all(obj)

    def test_real_activity_index_parity(self):
        idx = load_activity(config.DATASET_DIR)
        expected = {r["activity_id"]: r["event_time"] for r in idx.rows}
        self.assertEqual(activity_time_map(idx), expected)
        self.assertIs(activity_time_map(idx), activity_time_map(idx))


if __name__ == "__main__":
    unittest.main()

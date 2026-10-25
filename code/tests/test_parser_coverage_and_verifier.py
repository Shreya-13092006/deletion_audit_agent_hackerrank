"""Parser coverage over the raw logs, and the independent output verifier (evaluation/verify_output.py)."""
import csv
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts code/ on sys.path)
from helpers import real_auditor

from audit import config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
import verify_output  # noqa: E402

# Log events that name a resource but are not readings of its state (documented exceptions).
NOT_STATE_READINGS = {"thumbnail_failed"}          # attachment_preview service: rendering error only
RID = re.compile(r"resource_id\W{1,4}([a-z][a-z_]*_\d+)")
TS = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)")


def event_name(line: str) -> str:
    cols = [c.strip() for c in line.split("|")]
    if len(cols) > 5:                                  # "ts | LEVEL | service | trace | event | kv"
        return cols[4]
    m = re.search(r"event\W{1,4}([a-z_]+)", line) or re.search(r"\] ([a-z_]+):", line)
    return m.group(1) if m else "?"


class ParserCoverageTests(unittest.TestCase):
    def test_every_resource_log_line_becomes_an_evidence_card(self):
        """A log line naming a resource (other than *_started lookups) must yield an observation.

        This would have caught the unparsed `retained_order_loaded` event automatically.
        """
        auditor, _ = real_auditor()
        have = {(o.resource_id, o.observed_at) for o in auditor.store.observations}
        missing, checked = [], 0
        for path in sorted((config.DATASET_DIR / "evidence" / "logs").glob("*.log")):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                rid, ts = RID.search(line), TS.search(line)
                if not rid or not ts:
                    continue
                ev = event_name(line)
                if ev.endswith("_started") or ev in NOT_STATE_READINGS:
                    continue
                checked += 1
                if (rid.group(1), ts.group(1)) not in have:
                    missing.append((path.name, ev, rid.group(1), ts.group(1)))
        self.assertGreater(checked, 1000)
        self.assertEqual(missing, [])

    def test_retained_order_loaded_line_is_covered(self):
        auditor, _ = real_auditor()
        self.assertIn(("legal_hold_4961", "2026-07-03T07:57:01Z"),
                      {(o.resource_id, o.observed_at) for o in auditor.store.observations})


class VerifierTests(unittest.TestCase):
    def test_gold_sample_answers_pass_with_no_warnings(self):
        fails, warns, stats = verify_output.verify(config.DATASET_DIR / "sample_output.csv",
                                                   config.DATASET_DIR / "sample_deletion_requests.csv")
        self.assertEqual((fails, warns), ([], []))
        self.assertEqual(stats["rows"], 32)

    def test_submitted_output_has_no_hard_failures(self):
        fails, _, stats = verify_output.verify(config.REPO_ROOT / "output.csv",
                                               config.DATASET_DIR / "deletion_requests.csv")
        self.assertEqual(fails, [])
        self.assertEqual(stats["rows"], 518)

    def test_injected_violations_are_caught(self):
        with open(config.DATASET_DIR / "sample_output.csv", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        with open(config.DATASET_DIR / "evidence_files.csv", encoding="utf-8", newline="") as fh:
            late = max(csv.DictReader(fh), key=lambda m: m["captured_at"])["file_id"]
        by = {r["case_id"]: r for r in rows}
        steps = json.loads(by["case_01"]["steps_json"])
        steps[0]["evidence_id"] = "evidence_999"                       # unknown evidence
        by["case_01"]["steps_json"] = json.dumps(steps)
        steps = json.loads(by["case_05"]["steps_json"])
        steps[0]["evidence_id"] = late                                 # captured after audit_at
        by["case_05"]["steps_json"] = json.dumps(steps)
        by["case_06"]["deletion_status"] = "DONE"                      # invalid status
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.csv"
            with open(p, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"], lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            fails, _, _ = verify_output.verify(p, config.DATASET_DIR / "sample_deletion_requests.csv")
        text = " ".join(" ".join(f) for f in fails)
        self.assertIn("case_01 step 1 unknown evidence evidence_999", text)
        self.assertIn("case_05 step 1 cites", text)
        self.assertIn("case_06 status DONE", text)


if __name__ == "__main__":
    unittest.main()

"""Ghost Data Still Exists - deletion audit agent.

Usage (from the repository root):
    python code/main.py                     # 518 evaluation cases -> ./output.csv
    python code/main.py --split sample      # 32 public cases -> ./sample_predictions.csv
    python code/main.py --no-llm            # never call a model (cached results still used)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit.config import CACHE_DIR, DATASET_DIR, REPO_ROOT, TRAIL_PATH  # noqa: E402
from audit.llm import LLM  # noqa: E402
from audit.pipeline import Auditor, load_cases  # noqa: E402
from audit.planner import to_json  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402
from audit.validate import validate_rows  # noqa: E402

SPLITS = {"eval": ("deletion_requests.csv", "output.csv"),
          "sample": ("sample_deletion_requests.csv", "sample_predictions.csv")}


def case_key(case_id: str):
    head, _, num = case_id.rpartition("_")
    return (head, int(num)) if num.isdigit() else (case_id, 0)


def run(split: str, out: Path, use_llm: bool) -> list[dict]:
    trail = AuditTrail(TRAIL_PATH if split == "eval" else TRAIL_PATH.with_name(f"audit_trail_{split}.jsonl"))
    llm = LLM(CACHE_DIR / "intent_cache.json", enabled=use_llm, trail=trail)
    auditor = Auditor(DATASET_DIR, trail, llm)
    cases = load_cases(DATASET_DIR / SPLITS[split][0])
    # Account fallback is matched globally across every request the workflow reported on.
    all_cases = load_cases(DATASET_DIR / SPLITS["eval"][0]) + load_cases(DATASET_DIR / SPLITS["sample"][0])
    auditor.assign_workflow_resources(all_cases)
    rows = []
    for case in sorted(cases, key=lambda c: case_key(c.case_id)):
        decision = auditor.audit(case)
        rows.append({"case_id": case.case_id, "deletion_status": decision.status,
                     "steps_json": to_json(decision.steps), "_flags": decision.flags})
    problems = validate_rows(rows, cases, auditor.store.manifest, auditor.store.activity)
    for p in problems:
        trail.write("validation_problem", detail=p)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"],
                                extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    llm.save()
    llm.record_usage(f"{split}_run", len(rows))
    trail.flush()
    counts = {}
    for r in rows:
        counts[r["deletion_status"]] = counts.get(r["deletion_status"], 0) + 1
    print(f"wrote {len(rows)} rows to {out} {counts}; validation problems: {len(problems)}")
    for p in problems[:10]:
        print("  -", p)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=sorted(SPLITS), default="eval")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args(argv)
    out = args.out or REPO_ROOT / SPLITS[args.split][1]
    run(args.split, out, use_llm=not args.no_llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

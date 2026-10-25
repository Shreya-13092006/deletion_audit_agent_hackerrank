"""Score predictions against expected answers.

Usage (from the repository root):
    python code/evaluation/main.py                         # runs the sample split, then scores it
    python code/evaluation/main.py --pred sample_predictions.csv [--gold dataset/sample_output.csv] [-v]
    python code/evaluation/main.py --custom                # scores the hand-built custom cases

Metrics:
  status accuracy      exact deletion_status match per case
  step P/R/F1          multiset match of full steps (phase, system, resource, operation, state, evidence)
  step key F1          same, ignoring evidence_id (did we find the right work?)
  field accuracy       per-field agreement on steps aligned by step_no
  evidence accuracy    evidence_id agreement on steps whose key matches
  sequence accuracy    whole steps_json array identical (order included)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
REPO = CODE_DIR.parent
FIELDS = ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def load(path: Path) -> dict:
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def full(s):
    return tuple(s[f] for f in FIELDS[1:])


def key(s):
    return tuple(s[f] for f in FIELDS[1:6])


def prf(tp, n_pred, n_gold):
    p = tp / n_pred if n_pred else 1.0
    r = tp / n_gold if n_gold else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score(pred: dict, gold: dict, verbose=False) -> dict:
    m = Counter()
    field_hits, field_total = Counter(), Counter()
    failures = []
    for cid, (gstatus, gsteps) in sorted(gold.items()):
        pstatus, psteps = pred.get(cid, ("<missing>", []))
        m["cases"] += 1
        m["status_ok"] += pstatus == gstatus
        m["seq_ok"] += psteps == gsteps
        pf, gf = Counter(map(full, psteps)), Counter(map(full, gsteps))
        pk, gk = Counter(map(key, psteps)), Counter(map(key, gsteps))
        m["tp"] += sum((pf & gf).values())
        m["ktp"] += sum((pk & gk).values())
        m["npred"] += len(psteps)
        m["ngold"] += len(gsteps)
        gev = {key(s): s["evidence_id"] for s in gsteps}
        for s in psteps:
            if key(s) in gev:
                m["ev_total"] += 1
                m["ev_ok"] += s["evidence_id"] == gev[key(s)]
        for i in range(max(len(psteps), len(gsteps))):
            for f in FIELDS:
                field_total[f] += 1
                if i < len(psteps) and i < len(gsteps) and psteps[i][f] == gsteps[i][f]:
                    field_hits[f] += 1
        if psteps != gsteps or pstatus != gstatus:
            failures.append(cid)
            if verbose:
                print(f"\n## {cid}: pred {pstatus} / gold {gstatus}")
                for s in sorted(set(map(full, psteps)) - set(map(full, gsteps))):
                    print("   + extra  ", s)
                for s in sorted(set(map(full, gsteps)) - set(map(full, psteps))):
                    print("   - missing", s)
                if set(map(full, psteps)) == set(map(full, gsteps)):
                    print("   (same steps, different order)")
    p, r, f1 = prf(m["tp"], m["npred"], m["ngold"])
    kp, kr, kf1 = prf(m["ktp"], m["npred"], m["ngold"])
    return {
        "cases": m["cases"], "status_accuracy": m["status_ok"] / m["cases"],
        "step_precision": p, "step_recall": r, "step_f1": f1,
        "step_key_precision": kp, "step_key_recall": kr, "step_key_f1": kf1,
        "evidence_accuracy": m["ev_ok"] / m["ev_total"] if m["ev_total"] else 1.0,
        "field_accuracy": {f: field_hits[f] / field_total[f] for f in FIELDS if field_total[f]},
        "sequence_accuracy": m["seq_ok"] / m["cases"], "failures": failures,
    }


def print_report(name: str, res: dict) -> None:
    print(f"\n=== {name} ({res['cases']} cases) ===")
    print(f"status accuracy   {res['status_accuracy']:.3f}")
    print(f"step P/R/F1       {res['step_precision']:.3f} / {res['step_recall']:.3f} / {res['step_f1']:.3f}")
    print(f"step key P/R/F1   {res['step_key_precision']:.3f} / {res['step_key_recall']:.3f} / {res['step_key_f1']:.3f}")
    print(f"evidence accuracy {res['evidence_accuracy']:.3f}")
    print("field accuracy    " + ", ".join(f"{k}={v:.3f}" for k, v in res["field_accuracy"].items()))
    print(f"sequence accuracy {res['sequence_accuracy']:.3f}")
    print(f"failing cases     {', '.join(res['failures']) or 'none'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path)
    ap.add_argument("--gold", type=Path, default=REPO / "dataset" / "sample_output.csv")
    ap.add_argument("--custom", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.custom:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from custom_cases import run_custom_cases
        return run_custom_cases()
    pred_path = args.pred
    if pred_path is None:
        sys.path.insert(0, str(CODE_DIR))
        from main import run
        pred_path = REPO / "sample_predictions.csv"
        run("sample", pred_path, use_llm=False)
    res = score(load(pred_path), load(args.gold), args.verbose)
    print_report(f"{pred_path.name} vs {args.gold.name}", res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

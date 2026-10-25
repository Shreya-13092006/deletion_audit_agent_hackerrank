"""Ghost Data Still Exists - bounded agentic audit loop (ADR-002, docs/agent-loop-plan.md).

Same input and output contract as code/main.py (which stays the reference engine). Per case, a
planner picks read-only investigation tools from the case's open gaps until the evidence is
sufficient or a budget is hit; deterministic gates (incl. parity with the engine) decide what is
written. Writes one JSON card per case and an indexed evidence-card store for fast lookup.

Usage (from the repository root):
    python code/agent_main.py                        # 518 cases -> ./output.csv (rule planner, 0 model calls)
    python code/agent_main.py --split sample         # 32 cases -> ./sample_predictions_agent.csv
    python code/agent_main.py --split sample --planner gemini   # opt-in model planner (needs GEMINI_API_KEY)
    python code/agent_main.py --no-llm --rebuild-cards
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit import config  # noqa: E402
from audit.agent.cards import load_or_build  # noqa: E402
from audit.agent.loop import Budget, Orchestrator  # noqa: E402
from audit.agent.planner import GeminiPlanner, RulePlanner  # noqa: E402
from audit.agent.tools import ToolContext, build_registry  # noqa: E402
from audit.llm import LLM  # noqa: E402
from audit.pipeline import Auditor, load_cases  # noqa: E402
from audit.planner import to_json  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402
from audit.validate import validate_rows  # noqa: E402

SPLITS = {"eval": ("deletion_requests.csv", "output.csv", ""),
          "sample": ("sample_deletion_requests.csv", "sample_predictions_agent.csv", "_sample")}


def case_key(case_id: str):
    head, _, num = case_id.rpartition("_")
    return (head, int(num)) if num.isdigit() else (case_id, 0)


def run(split: str, out: Path, use_llm: bool, planner_name: str, budget: Budget,
        rebuild_cards: bool = False, cards_out: Path | None = None) -> dict:
    t0 = time.perf_counter()
    suffix = SPLITS[split][2]
    trail = AuditTrail(config.CACHE_DIR / f"audit_trail_agent{suffix}.jsonl")
    intent_llm = LLM(config.CACHE_DIR / "intent_cache.json", enabled=use_llm, trail=trail)
    cards = load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json",
                          config.EVIDENCE_CARDS_PATH, trail, rebuild=rebuild_cards)
    auditor = Auditor(config.DATASET_DIR, trail, intent_llm, store=cards.store)
    all_cases = load_cases(config.DATASET_DIR / SPLITS["eval"][0]) + \
        load_cases(config.DATASET_DIR / SPLITS["sample"][0])
    auditor.assign_workflow_resources(all_cases)        # global, one-to-one (engine logic)

    registry = build_registry()
    planner_llm = None
    if planner_name == "gemini":
        planner_llm = LLM(config.CACHE_DIR / "planner_cache.json", enabled=use_llm, trail=trail)
        planner = GeminiPlanner(registry, planner_llm, trail)
    else:
        planner = RulePlanner(registry)
    ctx = ToolContext.build(auditor, config.DATASET_DIR, cards)
    orch = Orchestrator(ctx, registry, planner, trail, budget)
    stamp = {"split": split, "planner": planner_name, "planner_model": config.PLANNER_MODEL if planner_llm else None,
             "intent_model": config.INTENT_MODEL, "llm_enabled": use_llm,
             "state_max_age_days": config.STATE_MAX_AGE_DAYS, "max_iterations": budget.max_iterations,
             "max_tool_calls": budget.max_tool_calls, "evidence_cards": cards.source,
             "evidence_fingerprint": cards.meta["fingerprint"][:16], "parse_errors": len(cards.store.errors)}
    trail.write("agent_run_config", **stamp)

    cases = load_cases(config.DATASET_DIR / SPLITS[split][0])
    rows, case_cards = [], {}
    for case in sorted(cases, key=lambda c: case_key(c.case_id)):
        decision, card = orch.run(case)
        rows.append({"case_id": case.case_id, "deletion_status": decision.status,
                     "steps_json": to_json(decision.steps)})
        case_cards[case.case_id] = card
    problems = validate_rows(rows, cases, auditor.store.manifest, auditor.store.activity)
    for p in problems:
        trail.write("validation_problem", detail=p)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"],
                                extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    review = sorted(cid for cid, c in case_cards.items() if c["review"]["required"])
    cards_path = cards_out or config.CACHE_DIR / f"case_cards{suffix}.json"
    cards_path.write_text(json.dumps({"meta": {**stamp, "stats": orch.stats, "review_queue": review},
                                      "cases": case_cards}, ensure_ascii=False, sort_keys=True, indent=1),
                          encoding="utf-8")
    intent_llm.save()
    intent_llm.record_usage(f"agent_{split}_intent", len(rows))
    if planner_llm is not None:
        planner_llm.save()
        planner_llm.record_usage(f"agent_{split}_planner", len(rows))
    trail.flush()

    if cards.store.errors:
        print(f"WARNING: {len(cards.store.errors)} evidence file(s) could not be parsed - their evidence is "
              "missing from this run and the output is NOT trustworthy:")
        for file_id, err in cards.store.errors:
            print(f"  - {file_id}: {err}")
    s = orch.stats
    counts: dict = {}
    for r in rows:
        counts[r["deletion_status"]] = counts.get(r["deletion_status"], 0) + 1
    eff = s["effective_calls"] / s["tool_calls"] if s["tool_calls"] else 0.0
    print(f"wrote {len(rows)} rows to {out} {counts}; validation problems: {len(problems)}")
    print("config: " + ", ".join(f"{k}={v}" for k, v in stamp.items()))
    print(f"agent: tool_calls={s['tool_calls']} (avg {s['tool_calls'] / max(s['cases'], 1):.1f}/case), "
          f"effectiveness={eff:.3f}, fallbacks={s['fallbacks']}, parity_diffs={s['parity_diffs']}, "
          f"unsupported_claims={s['unsupported_claims']}, contradictions={s['contradictions']}, "
          f"budget_exhausted={s['exhausted']}, review_queue={len(review)}, model_calls={s['model_calls']}, "
          f"planner_fallbacks={s['planner_fallbacks']}; case cards -> {cards_path.name}; "
          f"{time.perf_counter() - t0:.1f}s")
    for p in problems[:10]:
        print("  -", p)
    return {"rows": rows, "stats": s, "problems": problems, "review": review, "cards": case_cards,
            "parse_errors": list(cards.store.errors)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=sorted(SPLITS), default="eval")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--cards-out", type=Path, help="where to write the per-case cards JSON")
    ap.add_argument("--planner", choices=["rule", "gemini"], default="rule")
    ap.add_argument("--no-llm", action="store_true", help="never call a model (cached answers still used)")
    ap.add_argument("--max-iter", type=int, default=config.AGENT_MAX_ITERATIONS)
    ap.add_argument("--max-tools", type=int, default=config.AGENT_MAX_TOOL_CALLS)
    ap.add_argument("--rebuild-cards", action="store_true", help="re-parse evidence and rewrite evidence_cards.json")
    args = ap.parse_args(argv)
    out = args.out or config.REPO_ROOT / SPLITS[args.split][1]
    res = run(args.split, out, not args.no_llm, args.planner, Budget(args.max_iter, args.max_tools),
              args.rebuild_cards, args.cards_out)
    return 1 if res["problems"] or res["parse_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

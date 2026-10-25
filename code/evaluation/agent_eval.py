"""Evaluate the agent loop against the engine and the sample answers (ADR-002 §14).

Usage (from the repository root):
    python code/evaluation/agent_eval.py            # samples + custom agent cases -> agent_evaluation.md
    python code/evaluation/agent_eval.py --no-write

Reports, for engine (code/main.py logic) and agent (code/agent_main.py) on the 32 public samples:
status accuracy, step P/R/F1, evidence accuracy, sequence accuracy - overall and split into a
fixed 24-case tuning set and an 8-case hold-out (every 4th case). Agent-only metrics:
unsupported-claim rate, tool-use effectiveness, tool calls per case, fallbacks, parity diffs,
contradictions by kind and review-queue size. Then runs the hand-built agent cases C7-C9.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import sys
import tempfile
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
REPO = CODE_DIR.parent
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit import config  # noqa: E402
from audit.agent.loop import Budget, Orchestrator  # noqa: E402
from audit.agent.planner import RulePlanner  # noqa: E402
from audit.agent.tools import ToolContext, build_registry  # noqa: E402
from audit.planner import to_json  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402

HOLDOUT = {f"case_{i:02d}" for i in range(4, 33, 4)}      # fixed before any agent tuning


def _scorer():
    spec = importlib.util.spec_from_file_location("eval_scorer", Path(__file__).resolve().parent / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                         # read-only reuse of the starter scorer
    return mod


def _rows_to_pred(rows):
    import json
    return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in rows}


def _split(d, keep):
    return {k: v for k, v in d.items() if keep(k)}


def two_question_report(cards: dict, gold: dict, eng) -> list[str]:
    """Ownership vs state per step, sample precision per ownership tier, and why gold steps are missed."""
    import json as _json
    from audit.agent.ownership import classify_miss
    tier_hit = collections.defaultdict(lambda: [0, 0])
    state_n, scope_n, gaps = collections.Counter(), collections.Counter(), collections.Counter()
    for cid, card in cards.items():
        want = {(s["resource_id"], s["operation"]) for s in gold.get(cid, ("", []))[1]}
        for x in card["step_audit"]:
            t = x["ownership"]["tier"]
            tier_hit[t][0] += (x["resource_id"], x["operation"]) in want
            tier_hit[t][1] += 1
            state_n[x["state"]["basis"]] += 1
            if x["state"]["basis"] == "omission":
                scope_n[x["state"]["scope"] + (" (targeted)" if x["state"]["targeted"] else "")] += 1
        for gp in card["evidence_gaps"]:
            gaps[gp["kind"]] += 1
    participant = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in
                            (config.DATASET_DIR / "evidence").rglob("*") if p.is_file() and p.suffix not in (".png", ".pdf"))
    participant += (config.DATASET_DIR / "system_activity.csv").read_text(encoding="utf-8")
    for cache in ("image_facts.json", "pdf_text.json"):
        participant += (config.CACHE_DIR / cache).read_text(encoding="utf-8")
    misses = []
    for cid, (_, steps) in sorted(gold.items()):
        have = {(s["resource_id"], s["operation"]) for s in cards[cid]["decision"]["steps"]}
        for s in steps:
            if (s["resource_id"], s["operation"]) not in have:
                why = classify_miss(s["resource_id"], cid, participant, eng.tied_resources, eng.ambiguous_accounts)
                misses.append((cid, s["operation"], s["resource_id"], why))
    by_why = collections.Counter(m[3] for m in misses)
    lines = ["## Two questions per step (32 samples)", "",
             "Ownership (how the resource is tied to the requester) and state (what proves its state at audit_at) "
             "are reported separately. Tiers describe the basis; only G10 (findings need `proven`) uses them.", "",
             "| Ownership tier | Steps | Matching gold |", "|---|---|---|"]
    for t in ("proven", "proven-later", "inferred", "contested", "unlinked"):
        if tier_hit[t][1]:
            lines.append(f"| {t} | {tier_hit[t][1]} | {tier_hit[t][0]}/{tier_hit[t][1]} |")
    lines += ["", f"State basis: {dict(sorted(state_n.items()))}; omission scopes: {dict(sorted(scope_n.items()))}.",
              f"Evidence gaps recorded on case cards (not in output.csv): {dict(sorted(gaps.items()))}.", "",
              f"Missed gold steps: {len(misses)} = {dict(sorted(by_why.items()))}", ""]
    lines += [f"- {cid} {op} {rid}: **{why}**" for cid, op, rid, why in misses]
    return lines


def agent_custom_cases() -> list[tuple[str, bool, str]]:
    """C7-C9: synthetic cases on the custom-case auditor (fictional identities)."""
    from custom_cases import build_auditor, case, o
    results = []

    def agent(auditor, budget=None):
        for ob in auditor.store.observations:          # register the synthetic evidence files
            auditor.store.manifest.setdefault(ob.evidence_id, {"file_id": ob.evidence_id,
                                                                "captured_at": ob.captured_at})
        registry = build_registry()
        ctx = ToolContext(auditor)
        return Orchestrator(ctx, registry, RulePlanner(registry), AuditTrail(None), budget or Budget())

    # C7: workflow claims the profile was deleted; a later replica reading still serves it.
    a = build_auditor([
        o("ev_g", "2026-09-19T10:00:00Z", "account_83", "PRESENT", "USER_PROFILE", True,
          emails={"rowan.vale@example.test"}),
    ])
    a.store.activity.by_resource = {"account_83": [{
        "activity_id": "activity_c7", "event_time": "2026-09-11T11:00:00Z", "event_type": "DELETE_RECORD",
        "reported_result": "SUCCESS", "source_system": "deletion_worker", "target_system": "account_service",
        "resource_id": "account_83", "details": "Deleted account_83."}]}
    d, card = agent(a).run(case("Please delete my account."))
    ok = (d.status == "INCOMPLETE"
          and [(s.operation, s.resource_id) for s in d.steps][:2] == [("REPORT_REMAINING_RECORD", "account_83"),
                                                                    ("DELETE_RECORD", "account_83")]
          and any(c["kind"] == "claim_vs_evidence" for c in card["contradictions"])
          and card["decision"]["source"] == "agent")
    results.append(("C7 workflow claims DELETE success, later evidence shows the profile present", ok,
                    f"{d.status} ({card['decision']['source']}), contradictions={[c['kind'] for c in card['contradictions']]}"))

    # C8: security audit record whose supplied retention period has lapsed -> kept + human review.
    a = build_auditor([
        o("ev_h", "2026-09-19T10:00:00Z", "account_84", "ABSENT", "USER_PROFILE", emails={"rowan.vale@example.test"}),
        o("ev_h", "2026-09-19T10:00:00Z", "audit_record_84", "PRESENT", "SECURITY_AUDIT_LOG", users={"user_900"}),
    ])
    a.by_resource["audit_record_84"][0].attrs["retention_until"] = "2026-01-31T23:59:59Z"
    d, card = agent(a).run(case("Please delete my account."))
    ok = (d.status == "COMPLETE" and ("VERIFY_RECORD_PRESENT", "audit_record_84") in
          [(s.operation, s.resource_id) for s in d.steps]
          and "RETENTION_CONDITION_LAPSED:audit_record_84" in card["flags"] and card["review"]["required"]
          and card["decision"]["source"] == "agent")
    results.append(("C8 lapsed retention period is not auto-destroyed; it is flagged for human review", ok,
                    f"{d.status} ({card['decision']['source']}), review={card['review']['reasons']}"))

    # C9: a budget too small to finish falls back to the engine decision, flagged.
    a = build_auditor([
        o("ev_i", "2026-09-19T10:00:00Z", "account_85", "PRESENT", "USER_PROFILE", True,
          emails={"rowan.vale@example.test"}),
        o("ev_i", "2026-09-19T10:00:00Z", "search_85", "PRESENT", "SEARCH_INDEX_ENTRY", True,
          emails={"rowan.vale@example.test"}),
    ])
    c = case("Delete everything you hold about me.")
    d, card = agent(a, Budget(max_iterations=2, max_tool_calls=2)).run(c)
    engine = a.audit(c)
    ok = ((d.status, d.steps) == (engine.status, engine.steps) and card["decision"]["source"] == "fallback"
          and "AGENT_BUDGET_EXHAUSTED" in card["flags"])
    results.append(("C9 budget exhaustion falls back to the deterministic engine decision", ok,
                    f"{d.status}/{len(d.steps)} steps, source={card['decision']['source']}"))
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--planner", choices=["rule", "gemini"], default="rule",
                    help="gemini = billable model planner (needs GEMINI_API_KEY); answers are cached")
    args = ap.parse_args(argv)
    scorer = _scorer()
    gold = scorer.load(config.DATASET_DIR / "sample_output.csv")

    import agent_main
    from audit.pipeline import Auditor  # noqa: F401
    tmp = Path(tempfile.mkdtemp())
    res = agent_main.run("sample", tmp / "agent.csv", use_llm=args.planner == "gemini",
                         planner_name=args.planner, budget=Budget(),
                         cards_out=tmp / "cards.json")
    agent_pred = _rows_to_pred(res["rows"])
    # Engine answers for the same cases (the reference / fallback path).
    from audit.agent.cards import load_or_build
    from audit.pipeline import load_cases
    cards = load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", config.EVIDENCE_CARDS_PATH)
    eng = Auditor(config.DATASET_DIR, AuditTrail(None), None, store=cards.store)
    eng.assign_workflow_resources(load_cases(config.DATASET_DIR / "deletion_requests.csv") +
                                  load_cases(config.DATASET_DIR / "sample_deletion_requests.csv"))
    engine_rows = []
    for c in load_cases(config.DATASET_DIR / "sample_deletion_requests.csv"):
        d = eng.audit(c)
        engine_rows.append({"case_id": c.case_id, "deletion_status": d.status, "steps_json": to_json(d.steps)})
    engine_pred = _rows_to_pred(engine_rows)

    table = []
    for label, keep in (("all 32", lambda k: True), ("tune 24", lambda k: k not in HOLDOUT),
                        ("hold-out 8", lambda k: k in HOLDOUT)):
        g = _split(gold, keep)
        for name, pred in (("engine", engine_pred), ("agent", agent_pred)):
            m = scorer.score(_split(pred, keep), g)
            table.append((label, name, m))

    s = res["stats"]
    cited = sum(1 for card in res["cards"].values() for st in card["decision"]["steps"] if st["evidence_id"])
    kinds = collections.Counter(c["kind"] for card in res["cards"].values() for c in card["contradictions"])
    custom = agent_custom_cases()
    two_q = two_question_report(res["cards"], gold, eng)
    corr_calls = [t for card in res["cards"].values() for t in card["tool_calls"] if t["tool"] == "corroborate_evidence"]
    corr, corr_eff = len(corr_calls), sum(1 for t in corr_calls if t["closed_gaps"])
    downgraded = sorted(cid for cid, card in res["cards"].items() if card["decision"]["source"].endswith("proof_downgrade"))

    lines = ["# Agent loop evaluation (generated by `code/evaluation/agent_eval.py`)", "",
             f"Planner: {args.planner}, {res['stats']['model_calls']} model calls "
             f"({res['stats']['planner_fallbacks']} planner fallbacks to the rule choice). Hold-out = every 4th sample case "
             f"({', '.join(sorted(HOLDOUT))}), fixed before agent work; no agent parameter was tuned on any sample.", "",
             "| Split | Path | Status acc | Step P / R / F1 | Evidence acc | Sequence acc |",
             "|---|---|---|---|---|---|"]
    for label, name, m in table:
        lines.append(f"| {label} | {name} | {m['status_accuracy']:.3f} | {m['step_precision']:.3f} / "
                     f"{m['step_recall']:.3f} / {m['step_f1']:.3f} | {m['evidence_accuracy']:.3f} | "
                     f"{m['sequence_accuracy']:.3f} |")
    eff = s["effective_calls"] / s["tool_calls"] if s["tool_calls"] else 0.0
    lines += ["", "## Agent-only metrics (32 samples)", "",
              "| Metric | Value |", "|---|---|",
              f"| Unsupported-claim rate (cited steps whose evidence does not show the claimed state at audit_at) | "
              f"{s['unsupported_claims']}/{cited} = {s['unsupported_claims'] / cited if cited else 0:.3f} |",
              f"| Tool-use effectiveness (calls that added a fact or closed a gap) | {eff:.3f} |",
              f"| Tool calls per case | {s['tool_calls'] / s['cases']:.1f} |",
              f"| Fallbacks to engine / parity diffs / budget exhausted | {s['fallbacks']} / {s['parity_diffs']} / {s['exhausted']} |",
              f"| Contradictions surfaced | {dict(sorted(kinds.items()))} |",
              f"| Unresolved contradictions (sent to review) | {s['unresolved_contradictions']} |",
              f"| Corroboration calls (closed a gap / total) | {corr_eff}/{corr} |",
              f"| Proof-gate downgrades COMPLETE->INCOMPLETE | {s['proof_downgrades']} "
              f"({', '.join(downgraded) or 'none'}) |",
              f"| INCOMPLETE answers with an unsupported citation (review) | {s['unsupported_findings']} |",
              f"| Review queue | {len(res['review'])} ({', '.join(res['review']) or 'none'}) |",
              f"| Model calls | {s['model_calls']} |",
              f"| G10 findings without proven ownership | {s['g10_unproven_findings']} |",
              f"| FAILED claim vs omission-only absence (review) | {s.get('failed_claim_vs_omission', 0)} |",
              f"| Omission citations failing the snapshot-omission policy (G11) | {s['omission_scope_flags']} |",
              ""] + two_q + ["", "## Agent custom cases", ""]
    for name, ok, detail in custom:
        lines.append(f"- [{'PASS' if ok else 'FAIL'}] {name} - {detail}")
    text = "\n".join(lines) + "\n"
    print(text)
    if not args.no_write:
        name = "agent_evaluation.md" if args.planner == "rule" else f"agent_evaluation_{args.planner}.md"
        (Path(__file__).resolve().parent / name).write_text(text, encoding="utf-8")
    return 0 if all(ok for _, ok, _ in custom) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic safety and verification gates applied to every agent decision (G1-G8).

A decision that fails any blocking gate is replaced by the engine's decision for the case
(`Auditor.audit`), flagged `AGENT_GATE_FAIL:<gate>`, so output.csv can never be worse than the
proven baseline. The gate results are stored on the case card.
"""
from __future__ import annotations

from ..aliases import system_for
from ..linker import visible
from ..planner import to_json
from ..trail import AuditTrail
from ..validate import validate_rows

BLOCKING = ("G1_contract", "G2_time", "G3_claim_support", "G4_completion", "G5_not_applicable",
            "G6_no_mutation", "G8_parity")


def claim_support(ctx, state, steps) -> list[str]:
    """Steps that assert something the evidence does not show (unsupported claims)."""
    a = ctx.auditor
    audit_at = state.case.audit_at
    bad = []
    for s in steps:
        if s.resource_id not in state.linked:
            bad.append(f"{s.resource_id}:not_linked")
            continue
        if not s.evidence_id:
            continue
        obs_ok = any(o.evidence_id == s.evidence_id and visible(o, audit_at)
                     for o in a.by_resource.get(s.resource_id, []))
        cover_ok = any(c.evidence_id == s.evidence_id and c.system_id == system_for(s.resource_id)
                       and s.resource_id not in c.resource_ids and c.captured_at <= audit_at
                       for c in a.store.covers)
        if not (obs_ok or cover_ok):
            bad.append(f"{s.resource_id}:{s.evidence_id}:no_matching_fact")
    return bad


def run_gates(ctx, state, status: str, steps: list, registry: dict, planner) -> dict:
    a = ctx.auditor
    case = state.case
    gates: dict = {}
    row = {"case_id": case.case_id, "deletion_status": status, "steps_json": to_json(steps)}
    problems = validate_rows([row], [case], a.store.manifest, a.store.activity)
    time_problems = [p for p in problems if "captured after audit_at" in p or "unknown evidence" in p]
    other = [p for p in problems if p not in time_problems]
    gates["G1_contract"] = "pass" if not other else "fail:" + "; ".join(other[:3])
    gates["G2_time"] = "pass" if not time_problems else "fail:" + "; ".join(time_problems[:3])
    unsupported = claim_support(ctx, state, steps)
    gates["G3_claim_support"] = "pass" if not unsupported else "fail:" + "; ".join(unsupported[:5])
    complete_bad = status == "COMPLETE" and any(s.phase != "VERIFICATION" or not s.evidence_id for s in steps)
    gates["G4_completion"] = "pass" if not complete_bad else "fail:COMPLETE with finding/uncited step"
    na_bad = status == "NOT_APPLICABLE" and bool(steps)
    gates["G5_not_applicable"] = "pass" if not na_bad else "fail:NOT_APPLICABLE must be []"
    mutating = [t.name for t in registry.values() if t.permission != "read_evidence"]
    gates["G6_no_mutation"] = "pass" if not mutating else "fail:" + ",".join(mutating)
    rejected = getattr(planner, "rejections", 0)
    gates["G7_model_output"] = f"pass (rejected_answers_so_far={rejected})"
    # G8: the proven engine's answer for the same case, computed on a silent trail.
    saved_trail, a.trail = a.trail, AuditTrail(None)
    try:
        engine = a.audit(case)
    finally:
        a.trail = saved_trail
    same = engine.status == status and engine.steps == steps
    gates["G8_parity"] = "pass" if same else f"fail:engine={engine.status}/{len(engine.steps)} steps"
    return gates, engine, len(unsupported)

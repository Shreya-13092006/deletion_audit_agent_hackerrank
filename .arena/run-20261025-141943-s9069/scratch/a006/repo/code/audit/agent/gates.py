"""Deterministic safety and verification gates applied to every agent decision (G1-G9).

Two kinds of gate:
  * fallback gates (G1 contract, G5 not-applicable, G6 no mutation, G8 parity): an agent decision
    that fails one is replaced by the engine's decision (`Auditor.audit`), flagged
    `AGENT_GATE_FAIL:<gate>`.
  * proof gates (G2 time, G3 claim support, G4 completion shape, G9 completion proof): they are
    re-checked on whichever answer is finally chosen (agent or engine fallback), recomputed from
    the evidence cards rather than from the engine's resolved state. A COMPLETE answer that fails
    one is downgraded to INCOMPLETE with post-remediation checks (`downgrade`) and sent to review;
    an INCOMPLETE answer with an unsupported finding is flagged for review. Missing, stale or
    unreadable evidence never counts as proof.
The gate results are stored on the case card.
"""
from __future__ import annotations

from ..aliases import system_for
from ..config import STATE_MAX_AGE_DAYS
from ..linker import visible
from ..planner import plan, to_json
from ..policy import Treatment, required_action
from ..schema import ABSENT, ACTIVE, BLOCKED, DISABLED, PRESENT
from ..state import DOMINANCE, horizon_start
from ..trail import AuditTrail
from ..validate import validate_rows

FALLBACK_GATES = ("G1_contract", "G5_not_applicable", "G6_no_mutation", "G8_parity")
PROOF_GATES = ("G2_time", "G3_claim_support", "G4_completion", "G9_completion_proof")
BLOCKING = FALLBACK_GATES + PROOF_GATES

# What a step asserts about its resource: ("state", allowed states) or ("pii", visible?).
STEP_EXPECTS = {
    "REPORT_REMAINING_RECORD": ("state", {PRESENT}), "REPORT_EXPOSED_PII": ("pii", True),
    "REPORT_ACTIVE_DATA_FLOW": ("state", {ACTIVE}), "REPORT_RESTORE_RISK": ("state", {ACTIVE}),
    "VERIFY_RECORD_ABSENT": ("state", {ABSENT}), "VERIFY_RECORD_PRESENT": ("state", {PRESENT}),
    "VERIFY_RECORD_REDACTED": ("pii", False), "VERIFY_RECORD_ANONYMIZED": ("pii", False),
    "VERIFY_DATA_FLOW_DISABLED": ("state", {DISABLED}), "VERIFY_RESTORE_BLOCKED": ("state", {BLOCKED}),
}
# Final verification each required action must end in (record_type-specific first).
VERIFY_FOR_TYPE = {"BACKUP_ARCHIVE": "VERIFY_RESTORE_BLOCKED", "DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED"}
VERIFY_FOR_ACTION = {"DELETE": "VERIFY_RECORD_ABSENT", "REDACT": "VERIFY_RECORD_REDACTED",
                     "ANONYMIZE": "VERIFY_RECORD_ANONYMIZED", "RETAIN": "VERIFY_RECORD_PRESENT",
                     "DISABLE": "VERIFY_DATA_FLOW_DISABLED"}


def required_verification(rules: dict, record_type: str | None) -> str | None:
    if record_type in VERIFY_FOR_TYPE:
        return VERIFY_FOR_TYPE[record_type]
    return VERIFY_FOR_ACTION.get(required_action(rules, record_type))


def readings(a, rid: str, audit_at: str) -> list[dict]:
    """Every state reading of `rid` usable at audit_at: visible, within the freshness horizon.

    Absence by omission (a snapshot whose scope covers the system but lists no such record)
    counts only for a resource no evidence ever observed directly, as in state.resolve.
    """
    oldest = horizon_start(audit_at, STATE_MAX_AGE_DAYS)
    observations = a.by_resource.get(rid, [])
    out = [{"evidence_id": o.evidence_id, "at": o.observed_at, "state": o.state, "pii": o.pii,
            "replica": o.replica, "source": o.source}
           for o in observations
           if o.state != "LINK" and visible(o, audit_at) and o.observed_at >= oldest]
    if not any(o.state != "LINK" for o in observations):
        system = system_for(rid)
        for c in a.store.covers:
            if c.system_id == system and oldest <= c.captured_at <= audit_at and rid not in c.resource_ids:
                out.append({"evidence_id": c.evidence_id, "at": c.captured_at, "state": ABSENT, "pii": None,
                            "replica": "", "source": "snapshot_scope_omission"})
    return sorted(out, key=lambda r: (r["at"], r["evidence_id"], r["replica"]))


def evidence_basis(a, rid: str, audit_at: str) -> str:
    """Why a resource has (or lacks) a state at audit_at: fresh | stale | only_later | none."""
    if readings(a, rid, audit_at):
        return "fresh"
    observations = [o for o in a.by_resource.get(rid, []) if o.state != "LINK"]
    if any(visible(o, audit_at) for o in observations):
        return "stale"
    return "only_later" if observations else "none"


def _dominant(group: list[dict]) -> str:
    return max(group, key=lambda r: DOMINANCE.get(r["state"], 0))["state"]


def check_step(a, step, audit_at: str) -> str:
    """'' when the cited evidence supports the step's asserted state at audit_at, else a reason."""
    ev = step.evidence_id
    if any(file_id == ev for file_id, _ in a.store.errors):
        return "unreadable_evidence"
    rs = readings(a, step.resource_id, audit_at)
    cited = [r for r in rs if r["evidence_id"] == ev]
    if not cited:
        stale = any(o.evidence_id == ev and visible(o, audit_at) and o.state != "LINK"
                    for o in a.by_resource.get(step.resource_id, []))
        return "stale_evidence" if stale else "no_matching_fact"
    dim, want = STEP_EXPECTS[step.operation]
    if dim == "state":
        times = sorted({r["at"] for r in cited if r["state"] in want})
        if not times:
            return "state_mismatch"
        # At the cited time, any copy present means present; later readings must agree.
        if _dominant([r for r in rs if r["at"] == times[-1]]) not in want:
            return "state_mismatch:other_copy"
        latest = max(r["at"] for r in rs)
        if _dominant([r for r in rs if r["at"] == latest]) not in want:
            return "superseded_before_audit"
        return ""
    pii = [r for r in rs if r["pii"] is not None]
    if not any(r["pii"] is want for r in cited):
        return "pii_mismatch"
    latest = max(r["at"] for r in pii)
    shown = any(r["pii"] for r in pii if r["at"] == latest)
    return "" if shown is want else "pii_superseded_before_audit"


def claim_support(ctx, state, steps, linked=None) -> list[str]:
    """Steps that assert something the evidence does not show (unsupported claims)."""
    a = ctx.auditor
    linked = state.linked if linked is None else linked
    bad = []
    for s in steps:
        if s.resource_id not in linked:
            bad.append(f"{s.resource_id}:not_linked")
            continue
        if not s.evidence_id:
            continue
        problem = check_step(a, s, state.case.audit_at)
        if problem:
            bad.append(f"{s.resource_id}:{s.evidence_id}:{problem}")
    return bad


def completion_proof(ctx, state, status: str, steps, linked, primary) -> tuple[list[str], dict, list[str]]:
    """G9 for a COMPLETE answer: every linked record, flow and backup is accounted for.

    Returns (failures, accounting {rid: reason}, non-blocking notes).
    """
    if status != "COMPLETE":
        return [], {}, []
    a = ctx.auditor
    audit_at = state.case.audit_at
    by_rid: dict = {}
    for s in steps:
        by_rid.setdefault(s.resource_id, []).append(s)
    unresolved = {c["resource_id"] for c in state.contradictions if c["resolution"] == "unresolved"}
    failures, accounting, notes = [], {}, []
    if not primary:
        notes.append("primary_account_not_identified")
    for rid in sorted(linked):
        rtype = a.resolve_state(state.case, rid).record_type
        need = required_verification(a.rules, rtype)
        basis = evidence_basis(a, rid, audit_at)
        if rid in by_rid:
            ops = {s.operation for s in by_rid[rid]}
            if need and need not in ops:
                failures.append(f"{rid}:wrong_treatment:{sorted(ops)}!={need}")
            elif rid in unresolved:
                failures.append(f"{rid}:unresolved_contradiction")
            accounting[rid] = "verified"
            continue
        if rid == primary:
            # The subject's own profile is relevant whatever evidence linked it; a workflow
            # claim is not proof, so without a fresh reading its deletion is unproven.
            failures.append(f"{rid}:primary_account_unproven:{basis}_evidence")
        elif need is None:
            accounting[rid] = "no_policy_rule"
        elif basis == "only_later":
            # Contract: evidence created after audit_at must not change the answer.
            accounting[rid] = "only_later_evidence"
        elif basis in ("stale", "none"):
            failures.append(f"{rid}:{basis}_evidence")
        else:
            rs = readings(a, rid, audit_at)
            latest = max(r["at"] for r in rs)
            now = _dominant([r for r in rs if r["at"] == latest])
            if now == ABSENT and need not in ("VERIFY_RECORD_PRESENT",):
                accounting[rid] = "already_absent"
            elif need == "VERIFY_RECORD_PRESENT":
                failures.append(f"{rid}:retained_record_{now.lower()}")
            elif rtype in VERIFY_FOR_TYPE and now == ACTIVE:
                failures.append(f"{rid}:active_recreation_path")
            elif need in ("VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED"):
                pii = [r["pii"] for r in rs if r["pii"] is not None]
                failures.append(f"{rid}:{'pii_exposed' if pii and pii[-1] else 'pii_unknown'}")
            else:
                failures.append(f"{rid}:unaccounted:{now}")
    return failures, accounting, notes


def downgrade(ctx, state, items: list, failures: list[str], linked) -> list:
    """INCOMPLETE steps for a COMPLETE answer that failed a proof gate.

    Every treated record becomes a post-remediation check (empty evidence), and each record the
    proof gate could not account for gets the check its policy requires. Nothing is invented:
    no finding is emitted without evidence, and remediation is only proposed.
    """
    a = ctx.auditor
    have = {rs.resource_id for rs, _ in items}
    extra = []
    for f in failures:
        rid = f.split(":", 1)[0]
        if rid in have or rid not in linked:
            continue
        rs = a.resolve_state(state.case, rid)
        need = required_verification(a.rules, rs.record_type)
        if need:
            extra.append((rs, Treatment(None, None, need, "", future_only=True)))
            have.add(rid)
    _, steps = plan(list(items) + extra, force_incomplete=True)
    return steps


def engine_answer(a, case):
    """The proven engine's decision and its basis for the same case, on a silent trail."""
    saved_trail, a.trail = a.trail, AuditTrail(None)
    try:
        return a.audit(case), a.basis(case)
    finally:
        a.trail = saved_trail


def proof_gates(ctx, state, status: str, steps, linked, primary) -> tuple[dict, list, dict, list]:
    a = ctx.auditor
    case = state.case
    gates: dict = {}
    row = {"case_id": case.case_id, "deletion_status": status, "steps_json": to_json(steps)}
    problems = validate_rows([row], [case], a.store.manifest, a.store.activity)
    time_problems = [p for p in problems if "captured after audit_at" in p or "unknown evidence" in p]
    gates["G2_time"] = "pass" if not time_problems else "fail:" + "; ".join(time_problems[:3])
    unsupported = claim_support(ctx, state, steps, linked)
    gates["G3_claim_support"] = "pass" if not unsupported else "fail:" + "; ".join(unsupported[:5])
    complete_bad = status == "COMPLETE" and any(s.phase != "VERIFICATION" or not s.evidence_id for s in steps)
    gates["G4_completion"] = "pass" if not complete_bad else "fail:COMPLETE with finding/uncited step"
    failures, accounting, notes = completion_proof(ctx, state, status, steps, linked, primary)
    gates["G9_completion_proof"] = ("pass" if not failures else "fail:" + "; ".join(failures[:5])) + \
        (f" (notes: {', '.join(notes)})" if notes else "")
    state.proof_failures = unsupported + failures + time_problems + \
        (["shape:COMPLETE with finding/uncited step"] if complete_bad else [])
    return gates, unsupported, accounting, failures


def run_gates(ctx, state, status: str, steps: list, registry: dict, planner) -> tuple:
    a = ctx.auditor
    case = state.case
    gates: dict = {}
    row = {"case_id": case.case_id, "deletion_status": status, "steps_json": to_json(steps)}
    problems = validate_rows([row], [case], a.store.manifest, a.store.activity)
    other = [p for p in problems if not ("captured after audit_at" in p or "unknown evidence" in p)]
    gates["G1_contract"] = "pass" if not other else "fail:" + "; ".join(other[:3])
    proof, unsupported, accounting, _ = proof_gates(ctx, state, status, steps, state.linked, state.primary)
    gates.update(proof)
    na_bad = status == "NOT_APPLICABLE" and bool(steps)
    gates["G5_not_applicable"] = "pass" if not na_bad else "fail:NOT_APPLICABLE must be []"
    mutating = [t.name for t in registry.values() if t.permission != "read_evidence"]
    gates["G6_no_mutation"] = "pass" if not mutating else "fail:" + ",".join(mutating)
    rejected = getattr(planner, "rejections", 0)
    gates["G7_model_output"] = f"pass (rejected_answers_so_far={rejected})"
    # G8: the proven engine's answer for the same case.
    engine, basis = engine_answer(a, case)
    same = engine.status == status and engine.steps == steps
    gates["G8_parity"] = "pass" if same else f"fail:engine={engine.status}/{len(engine.steps)} steps"
    return gates, engine, len(unsupported), basis, accounting

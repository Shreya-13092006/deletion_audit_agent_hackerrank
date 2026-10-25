"""Build the ordered steps_json for a case from per-resource treatments.

Ordering contract: phase, then the operation table order, then system_id, then resource_id.
Evidence contract: findings and COMPLETE verifications cite the proving evidence; proposed
remediation and post-remediation verification (INCOMPLETE) use "".
"""
from __future__ import annotations

import json

from .config import OPERATION_ORDER, OPERATION_PHASE, OPERATION_STATE, PHASES
from .schema import Step

OP_RANK = {op: i for i, op in enumerate(OPERATION_ORDER)}


def plan(items: list, force_incomplete: bool = False) -> tuple[str, list[Step]]:
    """items: [(ResourceState, Treatment)]. Returns (status, steps)."""
    incomplete = force_incomplete or any(t.finding for _, t in items)
    steps: set[Step] = set()
    for rs, t in items:
        if incomplete:
            if t.finding:
                steps.add(_step(t.finding, rs, t.evidence_id))
                steps.add(_step(t.remediation, rs, ""))
            steps.add(_step(t.verification, rs, ""))
        elif not t.future_only:
            steps.add(_step(t.verification, rs, t.evidence_id))
    return ("INCOMPLETE" if incomplete else "COMPLETE"), sort_steps(steps)


def _step(op: str, rs, evidence_id: str) -> Step:
    return Step(OPERATION_PHASE[op], rs.system_id, rs.resource_id, op, OPERATION_STATE[op], evidence_id)


def sort_steps(steps) -> list[Step]:
    return sorted(steps, key=lambda s: (PHASES.index(s.phase), OP_RANK[s.operation], s.system_id,
                                        s.resource_id, s.evidence_id))


def to_json(steps: list[Step]) -> str:
    payload = [{"step_no": i, "phase": s.phase, "system_id": s.system_id, "resource_id": s.resource_id,
                "operation": s.operation, "state": s.state, "evidence_id": s.evidence_id}
               for i, s in enumerate(steps, start=1)]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

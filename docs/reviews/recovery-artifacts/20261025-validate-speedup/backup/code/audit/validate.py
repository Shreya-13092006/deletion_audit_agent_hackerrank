"""Output contract checks run before output.csv is written."""
from __future__ import annotations

import json

from .config import OPERATION_ORDER, OPERATION_PHASE, OPERATION_STATE, PHASES

STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


def validate_rows(rows: list[dict], cases: list, manifest: dict, activity) -> list[str]:
    problems = []
    audit_at = {c.case_id: c.audit_at for c in cases}
    activity_time = {r["activity_id"]: r["event_time"] for r in activity.rows} if activity else {}
    if len(rows) != len(cases) or {r["case_id"] for r in rows} != set(audit_at):
        problems.append("row set does not match the request file")
    for r in rows:
        cid, status = r["case_id"], r["deletion_status"]
        if status not in STATUSES:
            problems.append(f"{cid}: bad status {status}")
        steps = json.loads(r["steps_json"])
        if status == "NOT_APPLICABLE" and steps:
            problems.append(f"{cid}: NOT_APPLICABLE must have []")
        if status != "NOT_APPLICABLE" and not steps:
            problems.append(f"{cid}: {status} with no steps")
        last = (-1, -1)
        for i, s in enumerate(steps, start=1):
            if set(s) != KEYS or s["step_no"] != i:
                problems.append(f"{cid}: step {i} keys/numbering")
                continue
            if OPERATION_PHASE.get(s["operation"]) != s["phase"] or OPERATION_STATE.get(s["operation"]) != s["state"]:
                problems.append(f"{cid}: step {i} op/phase/state mismatch")
                continue
            rank = (PHASES.index(s["phase"]), OPERATION_ORDER.index(s["operation"]))
            if rank < last:
                problems.append(f"{cid}: step {i} out of order")
            last = rank
            ev = s["evidence_id"]
            needs_ev = s["phase"] == "FINDING" or status == "COMPLETE"
            if needs_ev and not ev:
                problems.append(f"{cid}: step {i} missing evidence")
            if not needs_ev and ev:
                problems.append(f"{cid}: step {i} future step must have empty evidence")
            if ev:
                when = manifest.get(ev, {}).get("captured_at") or activity_time.get(ev)
                if when is None:
                    problems.append(f"{cid}: step {i} unknown evidence {ev}")
                elif when > audit_at[cid]:
                    problems.append(f"{cid}: step {i} cites {ev} captured after audit_at")
    return problems

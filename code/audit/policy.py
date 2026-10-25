"""deletion_rules.csv applied per record_type (not per system).

`evaluate()` turns one resolved resource into its finding / remediation / verification
operations. Each returned item carries the evidence that proves the current state so the
planner can cite it for findings and for COMPLETE-case verification.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .schema import ABSENT, ACTIVE, BLOCKED, DISABLED, PRESENT
from .state import ResourceState

RETAINED_TYPES = {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}
# Treatments not expressed as a data_category row.
EXTRA_ACTIONS = {"DATA_FLOW": "DISABLE"}


@dataclass
class Treatment:
    finding: str | None          # REPORT_* operation or None when already compliant
    remediation: str | None
    verification: str
    evidence_id: str             # proves the current state (finding or compliant verification)
    note: str = ""
    future_only: bool = False    # usable only as a post-remediation check (no citable evidence)


def load_rules(dataset_dir: Path) -> dict:
    with open(dataset_dir / "deletion_rules.csv", encoding="utf-8", newline="") as fh:
        rules = {r["data_category"]: r for r in csv.DictReader(fh)}
    return rules


def required_action(rules: dict, record_type: str | None) -> str | None:
    if record_type in EXTRA_ACTIONS:
        return EXTRA_ACTIONS[record_type]
    row = rules.get(record_type or "")
    return row["required_action"] if row else None


def retention_condition(rs: ResourceState, audit_at: str) -> tuple[bool | None, str]:
    """Check the date condition behind a RETAIN rule at audit_at.

    rule_12 SECURITY_AUDIT_LOG: "within the supplied retention period" -> retention_until.
    rule_13 LEGAL_HOLD_RECORD: "a supplied legal hold is active" -> retained_until / hold_status.
    Returns (True, reason) when the condition holds, (False, reason) when the evidence shows it
    lapsed, (None, reason) when the evidence does not say. A lapsed or unknown condition never
    changes the treatment automatically: it is surfaced for human review (fail safe - a
    retained record is not destroyed on an uncertain reading of the policy).
    """
    if rs.record_type == "SECURITY_AUDIT_LOG":
        until = str(rs.attrs.get("retention_until") or "")
        if not until:
            return None, "retention_until not supplied"
        return (until >= audit_at), f"retention_until={until}"
    if rs.record_type == "LEGAL_HOLD_RECORD":
        status = str(rs.attrs.get("hold_status") or rs.attrs.get("status") or "").upper()
        if status in {"RELEASED", "INACTIVE", "EXPIRED", "CLOSED"}:
            return False, f"hold_status={status}"
        until = str(rs.attrs.get("retained_until") or "")
        if until:
            return (until >= audit_at), f"retained_until={until}"
        return (True if status == "ACTIVE" else None), f"hold_status={status or 'not supplied'}"
    return True, "no date condition"


def evaluate(rs: ResourceState, rules: dict) -> Treatment | None:
    action = required_action(rules, rs.record_type)
    if action is None or rs.state == "UNKNOWN":
        return None
    ev = rs.evidence_id
    if rs.record_type == "BACKUP_ARCHIVE":           # RETAIN, but restore must be blocked
        if rs.state == ACTIVE:
            return Treatment("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED", ev)
        if rs.state == BLOCKED:
            return Treatment(None, None, "VERIFY_RESTORE_BLOCKED", ev)
        return None
    if action == "DISABLE":
        if rs.state == ACTIVE:
            return Treatment("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED", ev)
        if rs.state == DISABLED:
            return Treatment(None, None, "VERIFY_DATA_FLOW_DISABLED", ev)
        return None
    if action == "DELETE":
        if rs.state == PRESENT:
            return Treatment("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT", ev)
        if rs.state == ABSENT:
            return Treatment(None, None, "VERIFY_RECORD_ABSENT", ev)
        return None
    if action in ("REDACT", "ANONYMIZE"):
        verify = "VERIFY_RECORD_REDACTED" if action == "REDACT" else "VERIFY_RECORD_ANONYMIZED"
        fix = "REDACT_RECORD" if action == "REDACT" else "ANONYMIZE_RECORD"
        if rs.state != PRESENT:
            return None
        if rs.pii:
            return Treatment("REPORT_EXPOSED_PII", fix, verify, rs.pii_evidence_id or ev)
        if rs.pii is False:
            return Treatment(None, None, verify, rs.pii_evidence_id or ev)
        return None
    if action == "RETAIN":
        if rs.state == PRESENT:
            return Treatment(None, None, "VERIFY_RECORD_PRESENT", ev)
        return None                                   # missing retained record: flagged upstream
    return None

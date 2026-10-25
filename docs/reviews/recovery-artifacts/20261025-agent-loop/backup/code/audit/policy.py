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

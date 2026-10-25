"""Guardrails: PII middleware, role-based capabilities, human-in-the-loop gate, fail-safe flags.

The agent is an *auditor*: it proposes remediation plans and never executes them. Every
capability is granted per pipeline role; anything outside a role raises PermissionError.
"""
from __future__ import annotations

import re

from .aliases import EMAIL_RE

PHONE_RE = re.compile(r"\+\d[\d\s\-()]{6,}\d")
HASH_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
USER_RE = re.compile(r"\buser_\d+\b")


def scrub_pii(text: str) -> str:
    """Replace direct identifiers with typed placeholders before text reaches a model."""
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = HASH_RE.sub("[HASH]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return USER_RE.sub("[USER_REF]", text)


ROLES = {
    "parser": {"read_evidence"},
    "resolver": {"read_identity", "read_evidence"},
    "classifier": {"read_request", "call_llm"},
    "planner": {"read_evidence", "propose_remediation"},
    "executor": {"execute_remediation"},          # never granted by the pipeline
}


class Capability:
    def __init__(self, role: str, trail=None):
        if role not in ROLES:
            raise PermissionError(f"unknown role {role!r}")
        self.role = role
        self.trail = trail

    def require(self, permission: str) -> None:
        if permission not in ROLES[self.role]:
            if self.trail:
                self.trail.write("permission_denied", role=self.role, permission=permission)
            raise PermissionError(f"role {self.role!r} lacks {permission!r}")


class ApprovalGate:
    """Human-in-the-loop: irreversible operations need an explicit approval token."""
    IRREVERSIBLE = {"DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD", "DISABLE_DATA_FLOW",
                    "BLOCK_RESTORE"}

    def __init__(self, trail=None):
        self.trail = trail
        self.approvals: set = set()

    def approve(self, case_id: str, approver: str) -> None:
        self.approvals.add(case_id)
        if self.trail:
            self.trail.write("approval_granted", case_id=case_id, approver=approver)

    def execute(self, case_id: str, step, capability: Capability) -> None:
        capability.require("execute_remediation")
        if step.operation in self.IRREVERSIBLE and case_id not in self.approvals:
            if self.trail:
                self.trail.write("execution_blocked", case_id=case_id, operation=step.operation)
            raise PermissionError(f"{step.operation} for {case_id} requires human approval")
        raise NotImplementedError("remediation execution is out of scope: plans are proposals only")


# Fail-safe flag names recorded on decisions and summarized in the evaluation report.
FLAG_IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
FLAG_IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
FLAG_ACCOUNT_INFERRED = "ACCOUNT_FROM_WORKFLOW_ACTIVITY"
FLAG_ACCOUNT_UNKNOWN = "ACCOUNT_UNRESOLVED"
FLAG_ACCOUNT_TIE = "ACCOUNT_WORKFLOW_TIME_ONLY_TIE"
FLAG_STATE_UNKNOWN = "STATE_UNKNOWN"
FLAG_RETAINED_MISSING = "RETAINED_RECORD_MISSING"
FLAG_INTENT_CONFLICT = "INTENT_CONFLICT"
FLAG_INTENT_LLM = "INTENT_FROM_LLM"
FLAG_RETAINED_LATER_EVIDENCE = "RETAINED_RECORD_ONLY_IN_LATER_EVIDENCE"
FLAG_NO_PROOF = "NO_CITABLE_PROOF_AT_AUDIT"
FLAG_CONTACT_CONFLICT = "RECORD_SHOWS_OTHER_CONTACT"

"""Per-case audit state: open/closed gaps, linked resources, facts, contradictions, budget.

`CaseState.to_card()` is the persisted per-case JSON card (docs/agent-loop-plan.md §5.1).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..schema import Case

# Investigation gaps in planner priority order (RulePlanner works top-down). Later gaps are only
# opened by tools that run after their prerequisites, so ordering constraints are structural:
# no planner (rule or model) can resolve a state before the subject's records are discovered.
GAP_ORDER = ["IDENTITY", "DISCOVERY", "LINKS", "INTENT", "ACCOUNT", "STATE", "REPLICA", "FLOW",
             "RESTORE", "RETENTION", "CORROBORATE", "VERIFY"]
GAP_RANK = {g: i for i, g in enumerate(GAP_ORDER)}
REVIEW_FLAG_PREFIXES = ("ACCOUNT_WORKFLOW_TIME_ONLY_TIE", "IDENTITY_AMBIGUOUS", "RECORD_SHOWS_OTHER_CONTACT",
                        "RETENTION_CONDITION_LAPSED", "INTENT_CONFLICT", "IDENTITY_HASH_MISMATCH",
                        "AGENT_", "FAILED_CLAIM_VS_OMISSION",
                        "ACCOUNT_ATTRIBUTION_REVIEW", "RECORD_CATEGORY_CONFLICT", "OMISSION_SCOPE_REVIEW")


@dataclass
class ToolCallRecord:
    iteration: int
    tool: str
    targets: list
    planner: str            # rule | gemini | rule_fallback
    reason: str
    new_facts: int
    closed_gaps: list
    opened_gaps: list
    contradictions: int

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CaseState:
    case: Case
    open_gaps: set = field(default_factory=lambda: {("IDENTITY", "")})
    closed_gaps: list = field(default_factory=list)     # [(kind, target, tool, iteration)]
    identity: object = None                            # schema.Identity
    identity_status: str = ""
    identity_provenance: list = field(default_factory=list)
    linked: dict = field(default_factory=dict)          # rid -> (rid, reason, evidence_id), ordered
    attributed: set = field(default_factory=set)
    primary: str | None = None
    intent: dict = field(default_factory=dict)
    not_applicable: bool = False
    resources: dict = field(default_factory=dict)       # rid -> state.ResourceState
    checks: dict = field(default_factory=dict)          # rid -> [check notes]
    contradictions: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    iterations: int = 0
    model_calls: int = 0
    exhausted: bool = False
    stop_reason: str = ""
    decision_status: str = ""
    decision_steps: list = field(default_factory=list)
    decision_source: str = ""
    gates: dict = field(default_factory=dict)
    handles: dict = field(default_factory=dict)         # rid -> opaque handle (model never sees ids)
    plan_items: list = field(default_factory=list)      # [(ResourceState, Treatment)] behind the steps
    no_progress: bool = False
    proof_failures: list = field(default_factory=list)  # G2/G3/G4/G9 reasons for the chosen answer
    proof_accounting: dict = field(default_factory=dict)  # rid -> why a COMPLETE answer covers it
    step_audit: list = field(default_factory=list)      # per step: ownership tier + state basis
    evidence_gaps: list = field(default_factory=list)   # what the evidence cannot establish

    # ---- gaps -------------------------------------------------------------------------------
    def open(self, kind: str, target: str = "") -> bool:
        gap = (kind, target)
        done = {(k, t) for k, t, _, _ in self.closed_gaps}
        if gap in self.open_gaps or gap in done:
            return False
        self.open_gaps.add(gap)
        if target and target not in self.handles:
            self.handles[target] = f"r{len(self.handles) + 1}"
        return True

    def close(self, kind: str, target: str, tool: str) -> None:
        self.open_gaps.discard((kind, target))
        self.closed_gaps.append((kind, target, tool, self.iterations))

    def open_kinds(self) -> list[str]:
        return sorted({k for k, _ in self.open_gaps}, key=GAP_RANK.__getitem__)

    def targets(self, kind: str) -> list[str]:
        return sorted(t for k, t in self.open_gaps if k == kind)

    def note(self, rid: str, text: str) -> None:
        self.checks.setdefault(rid, []).append(text)

    # ---- card -------------------------------------------------------------------------------
    def review_reasons(self) -> list[str]:
        reasons = sorted({f for f in self.flags if f.startswith(REVIEW_FLAG_PREFIXES)})
        reasons += [f"CONTRADICTION_UNRESOLVED:{c['resource_id']}" for c in self.contradictions
                    if c["resolution"] == "unresolved"]
        return reasons

    def to_card(self) -> dict:
        c = self.case
        ident = self.identity
        resources = {}
        for rid in sorted(self.linked):
            rs = self.resources.get(rid)
            _, reason, ev = self.linked[rid]
            resources[rid] = {
                "link": {"reason": reason, "evidence_id": ev},
                "system_id": rs.system_id if rs else "", "record_type": rs.record_type if rs else None,
                "state": rs.state if rs else None, "pii": rs.pii if rs else None,
                "state_evidence": rs.evidence_id if rs else "",
                "pii_evidence": rs.pii_evidence_id if rs else "",
                "timeline": [{"at": f.at, "state": f.state, "evidence_id": f.evidence_id, "pii": f.pii}
                             for f in (rs.facts if rs else [])],
                "checks": self.checks.get(rid, []),
                "primary_profile": rid == self.primary,
            }
        reasons = self.review_reasons()
        return {
            "case_id": c.case_id, "audit_at": c.audit_at, "requested_at": c.requested_at,
            "reported_status": c.reported_status, "reported_at": c.reported_at,
            "request_text_sha256": hashlib.sha256(c.request_text.encode("utf-8")).hexdigest(),
            "intent": self.intent,
            "identity": {"user_id": ident.user_id if ident else None, "status": self.identity_status,
                         "emails": sorted(ident.emails) if ident else [],
                         "hashes": sorted(ident.hashes) if ident else [],
                         "phones": sorted(ident.phones) if ident else [],
                         "provenance": self.identity_provenance},
            "resources": resources,
            "gaps": {"open": [list(g) for g in sorted(self.open_gaps)],
                     "closed": [list(g) for g in self.closed_gaps]},
            "contradictions": self.contradictions,
            "tool_calls": [t.as_dict() for t in self.tool_calls],
            "budget": {"iterations": self.iterations, "tool_calls": len(self.tool_calls),
                       "model_calls": self.model_calls, "exhausted": self.exhausted,
                       "stop_reason": self.stop_reason},
            "decision": {"status": self.decision_status, "source": self.decision_source,
                         "steps": [dict(step_no=i, phase=s.phase, system_id=s.system_id,
                                        resource_id=s.resource_id, operation=s.operation, state=s.state,
                                        evidence_id=s.evidence_id)
                                   for i, s in enumerate(self.decision_steps, start=1)]},
            "gates": self.gates,
            "proof": {"failures": self.proof_failures, "accounting": self.proof_accounting},
            "step_audit": self.step_audit,
            "evidence_gaps": self.evidence_gaps,
            "flags": self.flags,
            "review": {"required": bool(reasons), "reasons": reasons},
        }

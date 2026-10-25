"""Agent tools: read-only, idempotent wrappers over the tested engine (audit/*).

Contract (docs/agent-loop-plan.md §7): each tool declares the gap kind it closes and the
capability it needs; `run(ctx, state, targets)` updates the CaseState and returns a ToolResult.
No tool may need `execute_remediation` - the registry refuses such a tool (gate G6), so the
agent can only *propose* remediation, never perform it.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field

from .. import guardrails as g
from ..config import STATE_MAX_AGE_DAYS
from ..linker import link_by_identifier, propagate_links, visible
from ..policy import RETAINED_TYPES, retention_condition
from ..state import DOMINANCE, horizon_start

# Activity claims whose success implies a resource state (claims are never proof).
CLAIM_EXPECTS = {"DELETE_RECORD": ("state", "ABSENT"), "DISABLE_DATA_FLOW": ("state", "DISABLED"),
                 "BLOCK_RESTORE": ("state", "BLOCKED"), "REDACT_RECORD": ("pii", False),
                 "ANONYMIZE_RECORD": ("pii", False)}
PII_TYPES = {"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE", "ANALYTICS_PROFILE",
             "PRODUCT_TELEMETRY"}


@dataclass
class ToolResult:
    new_facts: int = 0
    closed: list = field(default_factory=list)
    opened: list = field(default_factory=list)
    contradictions: int = 0
    stop: str = ""                  # non-empty -> orchestrator stops (e.g. NOT_APPLICABLE)


@dataclass
class ToolContext:
    """Shared, read-only engine state for one run."""
    auditor: object                 # pipeline.Auditor (graph, store, rules, attribution)
    cards: object = None            # agent.cards.EvidenceCardStore (optional fast lookups)
    current_email: dict = field(default_factory=dict)   # user_id -> email in user_identities.csv
    audit_rows: dict = field(default_factory=dict)      # user_id -> [audit rows]

    @classmethod
    def build(cls, auditor, dataset_dir, cards=None) -> "ToolContext":
        ctx = cls(auditor, cards)
        with open(dataset_dir / "user_identities.csv", encoding="utf-8", newline="") as fh:
            ctx.current_email = {r["user_id"]: r["email"].strip().lower() for r in csv.DictReader(fh)}
        with open(dataset_dir / "user_audit_log.csv", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                ctx.audit_rows.setdefault(r["user_id"], []).append(r)
        return ctx


class Tool:
    name = ""
    gap = ""
    permission = "read_evidence"
    description = ""

    def run(self, ctx: ToolContext, state, targets: list) -> ToolResult:   # pragma: no cover
        raise NotImplementedError

    def _open(self, state, res: ToolResult, kind: str, target: str = "") -> None:
        if state.open(kind, target):
            res.opened.append([kind, target])

    def _close(self, state, res: ToolResult, kind: str, target: str = "") -> None:
        state.close(kind, target, self.name)
        res.closed.append([kind, target])


class ResolveIdentity(Tool):
    name, gap = "resolve_identity", "IDENTITY"
    description = "Resolve current + historical emails, sha256 hashes and user_id for the request email."

    def run(self, ctx, state, targets):
        res = ToolResult()
        ident, flags = ctx.auditor.identity_for(state.case)
        state.identity = ident
        state.flags += flags
        state.identity_status = ("AMBIGUOUS" if g.FLAG_IDENTITY_AMBIGUOUS in flags else
                                 "UNRESOLVED" if g.FLAG_IDENTITY_UNRESOLVED in flags else "RESOLVED")
        if state.identity_status == "RESOLVED":
            uid = ident.user_id
            if uid in ctx.auditor.graph.hash_mismatches:
                state.flags.append(f"IDENTITY_HASH_MISMATCH:{uid}")
            prov = [{"identifier": ctx.current_email.get(uid, ""), "kind": "email",
                     "source": "user_identities.csv"}]
            for r in ctx.audit_rows.get(uid, []):
                if r["field_name"] in ("email", "email_hash"):
                    for v in (r["old_value"], r["new_value"]):
                        if v and v.strip():
                            prov.append({"identifier": v.strip().lower(), "kind": r["field_name"],
                                         "source": f"user_audit_log.csv:{r['audit_id']}"})
            state.identity_provenance = prov
        res.new_facts = len(ident.identifiers)
        self._close(state, res, "IDENTITY")
        self._open(state, res, "DISCOVERY")
        return res


class SearchEvidence(Tool):
    name, gap = "search_evidence", "DISCOVERY"
    description = "Find every resource whose evidence carries the subject's exact email, hash or user_id."

    def run(self, ctx, state, targets):
        res = ToolResult()
        found = link_by_identifier(state.identity, ctx.auditor.store, state.case.audit_at)
        for rid, prov in found.items():
            if rid not in state.linked:
                state.linked[rid] = prov
                res.new_facts += 1
        self._close(state, res, "DISCOVERY")
        self._open(state, res, "LINKS")
        return res


class FollowLinks(Tool):
    name, gap = "follow_links", "LINKS"
    description = "Follow search->account source links and sync/restore repopulation paths to a fixpoint."

    def run(self, ctx, state, targets):
        res = ToolResult()
        a = ctx.auditor
        added = propagate_links(state.linked, state.identity, a.store, state.case.audit_at, a.by_resource)
        res.new_facts = len(added)
        self._close(state, res, "LINKS")
        self._open(state, res, "INTENT")
        return res


class ClassifyIntent(Tool):
    name, gap = "classify_intent", "INTENT"
    description = "Decide whether request_text authorizes deletion (rules first; model only if undecided)."

    def run(self, ctx, state, targets):
        res = ToolResult()
        authorized, flags, reason = ctx.auditor.intent_for(state.case, set(state.linked))
        state.flags += flags
        state.intent = {"authorized": authorized, "reason": reason, "flags": list(flags)}
        self._close(state, res, "INTENT")
        if not authorized:
            state.not_applicable = True
            res.stop = "NOT_APPLICABLE"
        else:
            self._open(state, res, "ACCOUNT")
        return res


class AttributeWorkflow(Tool):
    name, gap = "attribute_workflow", "ACCOUNT"
    description = "Add identity-less records the deletion workflow acted on (flagged heuristic)."

    def run(self, ctx, state, targets):
        res = ToolResult()
        before = set(state.linked)
        linked, attributed, primary = ctx.auditor.attribute(state.case, set(state.linked), state.flags)
        for rid in sorted(linked - before):
            state.linked[rid] = (rid, "workflow_attribution", "")
            res.new_facts += 1
        state.attributed, state.primary = attributed, primary
        self._close(state, res, "ACCOUNT")
        for rid in sorted(state.linked):
            self._open(state, res, "STATE", rid)
        return res


class ReconstructTimeline(Tool):
    name, gap = "reconstruct_timeline", "STATE"
    description = "Resolve each resource's state at audit_at from its observation timeline."

    def run(self, ctx, state, targets):
        res = ToolResult()
        a = ctx.auditor
        recreation_sources = {s for s, _, _ in a.store.activity.recreation_links}
        for rid in targets:
            rs = a.resolve_state(state.case, rid)
            state.resources[rid] = rs
            res.new_facts += len(rs.facts)
            res.contradictions += _timeline_contradictions(state, rid, rs)
            res.contradictions += _claim_contradictions(ctx, state, rid, rs)
            self._close(state, res, "STATE", rid)
            if any(o.replica for o in a.by_resource.get(rid, [])):
                self._open(state, res, "REPLICA", rid)
            if rs.record_type == "DATA_FLOW" or rid in recreation_sources:
                self._open(state, res, "FLOW", rid)
            if rs.record_type == "BACKUP_ARCHIVE":
                self._open(state, res, "RESTORE", rid)
            if rs.record_type in RETAINED_TYPES or rs.record_type in PII_TYPES:
                self._open(state, res, "RETENTION", rid)
        return res


class CheckReplicas(Tool):
    name, gap = "check_replicas", "REPLICA"
    description = "Compare primary and replica copies in each snapshot (any copy present = present)."

    def run(self, ctx, state, targets):
        res = ToolResult()
        a = ctx.auditor
        audit_at = state.case.audit_at
        oldest = horizon_start(audit_at, STATE_MAX_AGE_DAYS)
        for rid in targets:
            per_file: dict = {}
            for o in a.by_resource.get(rid, []):
                if o.replica and o.state != "LINK" and visible(o, audit_at) and o.observed_at >= oldest:
                    per_file.setdefault(o.evidence_id, {})[o.replica] = o.state
            for ev, copies in sorted(per_file.items()):
                # Tables in the same snapshot file (fast lookup through the evidence-card index):
                # a table that holds other records of this system but not this one is a missing copy.
                system = state.resources[rid].system_id if rid in state.resources else ""
                tables = _tables_in_file(ctx, ev, system)
                if not tables or not set(copies) <= tables:
                    continue                    # not a primary/replica snapshot of this record
                full = {t: copies.get(t, "MISSING") for t in sorted(tables)}
                if len(full) > 1 and len(set(full.values())) > 1:
                    present = any(v in ("PRESENT", "ACTIVE") for v in full.values())
                    state.contradictions.append({
                        "resource_id": rid, "kind": "primary_vs_replica", "evidence": [ev], "copies": full,
                        "resolution": "any_replica_present",
                        "resolved_state": "PRESENT" if present else state.resources[rid].state})
                    res.contradictions += 1
            state.note(rid, f"replicas_checked:{len(per_file)}_files")
            self._close(state, res, "REPLICA", rid)
        return res


COPY_WORDS = ("primary", "replica", "failover")


def _tables_in_file(ctx, evidence_id: str, system: str) -> set:
    """Copy tables (primary / replica / failover) of one snapshot file.

    Only genuine copy tables are compared: inventory snapshots name each *collection* as its
    own table, and a record missing from a different collection is not a missing copy.
    """
    if ctx.cards is not None:
        names = {c["replica"] for c in ctx.cards.cards_for_evidence(evidence_id) if c["replica"]}
    else:
        names = {o.replica for o in ctx.auditor.store.observations if o.evidence_id == evidence_id and o.replica}
    return {n for n in names if any(w in n for w in COPY_WORDS)}


class CheckSyncPaths(Tool):
    name, gap = "check_sync_paths", "FLOW"
    description = "Check whether an active sync/import/replication path can recreate deleted data."

    def run(self, ctx, state, targets):
        res = ToolResult()
        a = ctx.auditor
        for rid in targets:
            rs = state.resources.get(rid)
            downstream = sorted({d for s, d, row in a.store.activity.recreation_links
                                 if s == rid and row["event_time"] <= state.case.audit_at})
            state.note(rid, f"flow_state:{rs.state if rs else 'UNKNOWN'}")
            for d in downstream:
                state.note(rid, f"repopulated:{d}")
                if d in state.linked and d not in state.resources:
                    self._open(state, res, "STATE", d)
            res.new_facts += len(downstream)
            self._close(state, res, "FLOW", rid)
        return res


class CheckBackupRestore(Tool):
    name, gap = "check_backup_restore", "RESTORE"
    description = "Check whether a backup can still restore the subject's data, or restore is blocked."

    def run(self, ctx, state, targets):
        res = ToolResult()
        for rid in targets:
            rs = state.resources.get(rid)
            state.note(rid, f"restore_state:{rs.state if rs else 'UNKNOWN'}")
            restores = [r for r in ctx.auditor.store.activity.by_resource.get(rid, [])
                        if r["event_type"] == "RESTORE_BACKUP" and r["event_time"] <= state.case.audit_at]
            for r in restores:
                state.note(rid, f"restore_event:{r['activity_id']}")
            res.new_facts += len(restores)
            self._close(state, res, "RESTORE", rid)
        return res


class CheckRetentionPII(Tool):
    name, gap = "check_retention_pii", "RETENTION"
    description = "Check retention/legal-hold date conditions and which identifiers a kept record still shows."

    def run(self, ctx, state, targets):
        res = ToolResult()
        for rid in targets:
            rs = state.resources.get(rid)
            if rs is None:
                self._close(state, res, "RETENTION", rid)
                continue
            if rs.record_type in RETAINED_TYPES and rs.state != "UNKNOWN":
                ok, why = retention_condition(rs, state.case.audit_at)
                state.note(rid, f"retention:{'ok' if ok else 'lapsed' if ok is False else 'unknown'}:{why}")
                if ok is False:
                    state.flags.append(f"RETENTION_CONDITION_LAPSED:{rid}")
            if rs.record_type in PII_TYPES:
                state.note(rid, f"identifiers_visible:{rs.pii}")
            self._close(state, res, "RETENTION", rid)
            res.new_facts += 1
        return res


class VerifyPlan(Tool):
    name, gap = "verify_plan", "VERIFY"
    description = "Apply deletion_rules.csv to every resolved record and build the ordered steps."

    def run(self, ctx, state, targets):
        res = ToolResult()
        a = ctx.auditor
        a.planner_cap.require("propose_remediation")
        items = []
        for rid in sorted(state.linked):
            rs = state.resources.get(rid) or a.resolve_state(state.case, rid)
            item = a.treat(rid, rs, state.primary, state.flags)
            if item is not None:
                items.append(item)
        status, steps = a.finalize(items, state.flags)
        state.decision_status, state.decision_steps, state.decision_source = status, steps, "agent"
        if state.case.reported_status == "COMPLETE" and status == "INCOMPLETE":
            state.contradictions.append({"resource_id": "", "kind": "status_vs_findings",
                                         "evidence": [], "resolution": "evidence_over_claim",
                                         "resolved_state": status})
            res.contradictions += 1
        res.new_facts = len(steps)
        self._close(state, res, "VERIFY")
        return res


def _timeline_contradictions(state, rid, rs) -> int:
    n, prev = 0, None
    for f in rs.facts:
        exists = {"PRESENT": True, "ABSENT": False}.get(f.state)
        if exists is None:
            continue
        if prev is not None and prev[0] != exists:
            state.contradictions.append({
                "resource_id": rid, "kind": "found_then_not_found" if prev[0] else "not_found_then_found",
                "at": f.at, "evidence": [prev[1], f.evidence_id], "resolution": "latest_valid",
                "resolved_state": rs.state})
            n += 1
        prev = (exists, f.evidence_id)
    return n


def _claim_contradictions(ctx, state, rid, rs) -> int:
    """An operation the workflow *claims* succeeded, contradicted by a later evidence reading."""
    n = 0
    for row in ctx.auditor.store.activity.by_resource.get(rid, []):
        expect = CLAIM_EXPECTS.get(row["event_type"])
        if not expect or row["reported_result"] != "SUCCESS" or row["event_time"] > state.case.audit_at:
            continue
        later = [f for f in rs.facts if f.at > row["event_time"]]
        if not later:
            continue                    # no reading after the claim: unverified, not contradicted
        field_, want = expect
        last = later[-1]
        if (field_ == "state" and last.state != want) or (field_ == "pii" and last.pii is True):
            state.contradictions.append({
                "resource_id": rid, "kind": "claim_vs_evidence", "at": last.at,
                "evidence": [row["activity_id"], last.evidence_id], "claim": row["event_type"],
                "resolution": "evidence_over_claim", "resolved_state": rs.state})
            n += 1
    return n


def build_registry() -> dict:
    tools = [ResolveIdentity(), SearchEvidence(), FollowLinks(), ClassifyIntent(), AttributeWorkflow(),
             ReconstructTimeline(), CheckReplicas(), CheckSyncPaths(), CheckBackupRestore(),
             CheckRetentionPII(), VerifyPlan()]
    registry = {}
    reader = g.Capability("planner")            # the agent's role: read + propose only
    for tool in tools:
        if tool.permission == "execute_remediation":
            raise PermissionError(f"tool {tool.name} would mutate external systems (gate G6)")
        reader.require(tool.permission)
        registry[tool.name] = tool
    return registry


def tool_for_gap(registry: dict) -> dict:
    return {t.gap: t.name for t in registry.values()}

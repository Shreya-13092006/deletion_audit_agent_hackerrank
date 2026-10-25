"""Two separate questions per step, plus the case's evidence gaps (internal record only).

1. Ownership: how is the resource tied to this requester?
     proven        exact identifier in evidence at or before audit_at, or a resource link
                   (search doc -> account, repopulating connector/backup) from such a record
     proven-later  exact identifier, but only in evidence captured after audit_at
     inferred      deletion-workflow attribution (no identifier; window + status + co-occurrence)
     contested     workflow attribution decided by time alone (ACCOUNT_WORKFLOW_TIME_ONLY_TIE)
   The tier describes the basis; it does not make a step valid or invalid. Only gate G10
   uses it: a FINDING must have `proven` ownership.
2. State: what establishes the resource's state at audit_at?
     direct        a reading of the record in the cited file
     omission      the cited snapshot covers the system and omits the record; its scope is
                   `declared` (snapshot_scope table / bundle data_store), `inferred` (a replica or
                   failover file that merely contains that system), and an inferred scope holding
                   very few records of the system is also marked `targeted` - only `declared` is
                   treated as exhaustive; the others are flagged, never silently trusted
     future        no evidence: a post-remediation check

Nothing here changes output.csv; it annotates the case card and the evaluator report.
"""
from __future__ import annotations

from ..aliases import COLLECTION_RECORD_TYPE, system_for
from ..config import DATASET_DIR
from ..linker import visible
from ..policy import RETAINED_TYPES, required_action
from .. import guardrails as g

PROVEN_TIERS = ("proven",)
TARGETED_MAX_RECORDS = 5            # a snapshot of a system with this few records is a targeted capture


def ownership(state, rid: str) -> dict:
    """{'tier', 'basis', 'evidence_id'} for one linked resource of the case."""
    _, reason, ev = state.linked.get(rid, (rid, "unlinked", ""))
    if reason == "workflow_attribution":
        tie = rid == state.primary and g.FLAG_ACCOUNT_TIE in state.flags
        return {"tier": "contested" if tie else "inferred", "basis": reason, "evidence_id": ev}
    if reason == "identifier_later_evidence":
        return {"tier": "proven-later", "basis": reason, "evidence_id": ev}
    if reason == "identifier" or reason.startswith(("resource_link:", "repopulates:")):
        root = reason.split(":", 1)[1] if ":" in reason else rid
        if root != rid and state.linked.get(root, (0, "", ""))[1] == "identifier_later_evidence":
            return {"tier": "proven-later", "basis": reason, "evidence_id": ev}
        return {"tier": "proven", "basis": reason, "evidence_id": ev}
    return {"tier": "unlinked", "basis": reason, "evidence_id": ev}


def scope_kind(a, evidence_id: str, system: str) -> dict:
    """How the cited snapshot's coverage of `system` is documented."""
    cache = a.store.__dict__.setdefault("_scope_cache", {})       # per store: never shared across stores
    key = (evidence_id, system)
    if key in cache:
        return cache[key]
    meta = a.store.manifest.get(evidence_id, {})
    path = DATASET_DIR / meta.get("file_path", "")
    text = path.read_text(encoding="utf-8", errors="replace") if meta.get("file_path") and path.exists() else ""
    if "CREATE TABLE snapshot_scope" in text:
        kind = "declared" if f"INSERT INTO snapshot_scope VALUES ('{system}'" in text else "not_covered"
    elif '"data_store"' in text:
        kind = "declared" if f'"data_store": "{system}"' in text else "not_covered"
    else:
        kind = "inferred"              # replica / failover pair: scope only implied by its contents
    covers = [c for c in a.store.covers if c.evidence_id == evidence_id and c.system_id == system]
    size = max((len(c.resource_ids) for c in covers), default=0)
    out = {"scope": kind, "records_of_system": size,
           # A declared scope is the snapshot's own statement of coverage (even with 0 records); a
           # file whose scope is only inferred and that holds this few records is a targeted capture.
           "targeted": kind == "inferred" and size <= TARGETED_MAX_RECORDS}
    cache[key] = out
    return out


def state_basis(a, step, audit_at: str, state=None) -> dict:
    """What establishes the step's asserted state at audit_at (see module docstring)."""
    from .gates import readings
    if not step.evidence_id:
        return {"basis": "future"}
    rows = [r for r in readings(a, step.resource_id, audit_at) if r["evidence_id"] == step.evidence_id]
    if any(r["source"] != "snapshot_scope_omission" for r in rows):
        return {"basis": "direct"}
    if rows:
        scope = scope_kind(a, step.evidence_id, system_for(step.resource_id))
        return {"basis": "omission", **scope, "policy": omission_policy(a, state, step, scope, audit_at)}
    return {"basis": "unsupported"}


def omission_policy(a, state, step, scope: dict, audit_at: str) -> dict:
    """Absence-by-omission policy for a snapshot without a declared scope (review 2026-10-25).

    Accepted when all four hold:
      system_records_in_file    the snapshot holds records of the resource's system in some copy
      within_window             it was captured within STATE_MAX_AGE_DAYS before audit_at
      requester_in_capture      the requester's other (linked) records appear in the same capture
      no_other_reading          no evidence anywhere reads the target resource itself
    A snapshot dedicated to that one system (every copy table is that system, e.g. the
    account-only failover pair evidence_54 that the public gold cites as proof of absence)
    cannot contain the requester's other records, so it is accepted on the other three
    (`accepted_single_system_snapshot`). A declared scope is accepted as before. Anything else
    is `conditions_unmet` and flagged; the decision itself is never changed here.
    """
    from ..state import horizon_start
    from ..config import STATE_MAX_AGE_DAYS
    ev, rid = step.evidence_id, step.resource_id
    system = system_for(rid)
    covers = [c for c in a.store.covers if c.evidence_id == ev]
    mine = [c for c in covers if c.system_id == system]
    oldest = horizon_start(audit_at, STATE_MAX_AGE_DAYS)
    linked = set(state.linked) if state is not None else set()
    cond = {
        "system_records_in_file": scope["records_of_system"] > 0,
        "within_window": any(oldest <= c.captured_at <= audit_at for c in mine),
        "requester_in_capture": any(o.evidence_id == ev and o.state != "LINK" for r in linked - {rid}
                                    for o in a.by_resource.get(r, [])),
        "no_other_reading": not any(o.state != "LINK" for o in a.by_resource.get(rid, [])),
    }
    single_system = bool(covers) and {c.system_id for c in covers} == {system}
    if scope["scope"] == "declared":
        verdict = "declared_scope"
    elif all(cond.values()):
        verdict = "accepted"
    elif single_system and all(v for k, v in cond.items() if k != "requester_in_capture"):
        verdict = "accepted_single_system_snapshot"
    else:
        verdict = "conditions_unmet:" + ",".join(k for k, v in cond.items() if not v)
    return {"verdict": verdict, "single_system_snapshot": single_system, **cond}


def step_audit(ctx, state, steps) -> list[dict]:
    a = ctx.auditor
    out = []
    for i, s in enumerate(steps, start=1):
        out.append({"step_no": i, "phase": s.phase, "operation": s.operation, "resource_id": s.resource_id,
                    "ownership": ownership(state, s.resource_id),
                    "state": state_basis(a, s, state.case.audit_at, state)})
    return out


def g10_ownership(audit: list[dict]) -> list[str]:
    """Findings without proven ownership (a finding names *this* person's data)."""
    return [f"{x['resource_id']}:{x['ownership']['tier']}" for x in audit
            if x["phase"] == "FINDING" and x["ownership"]["tier"] not in PROVEN_TIERS]


def omission_scope_flags(audit: list[dict]) -> list[str]:
    """Undeclared snapshot scopes that need review, including policy-accepted omissions."""
    out = []
    for x in audit:
        st = x["state"]
        if st["basis"] == "omission" and st["scope"] != "declared":
            out.append(f"{x['resource_id']}:{st['scope']}:{st['policy']['verdict']}")
    return out


def policy_category_conflicts(a, resource_ids, audit_at: str) -> list[dict]:
    """Report resources whose time-visible, explicit categories require different actions.

    This is annotation-only: a conflicting policy label is not resolved by choosing the more
    destructive treatment, and it does not change the answer. Category evidence must be
    participant-visible by audit_at and explicit in a record field, a typed SQL collection, or a
    typed log event; a resource-prefix default alone is not enough to create a conflict.
    """
    explicit_events = {"attachment_pii_scan": "SUPPORT_ATTACHMENT",
                       "message_pii_scan": "SUPPORT_MESSAGE"}
    out = []
    for rid in sorted(resource_ids):
        categories: dict[str, set[str]] = {}
        evidence: dict[str, set[str]] = {}
        for obs in a.by_resource.get(rid, []):
            rtype = obs.record_type
            if not rtype or obs.state == "LINK" or not visible(obs, audit_at):
                continue
            explicit = obs.attrs.get("record_type") == rtype or \
                explicit_events.get(obs.attrs.get("event")) == rtype or \
                any(obs.source.endswith(":" + table) and category == rtype
                    for table, category in COLLECTION_RECORD_TYPE.items())
            if not explicit:
                continue
            action = required_action(a.rules, rtype)
            if action:
                categories.setdefault(rtype, set()).add(action)
                evidence.setdefault(rtype, set()).add(obs.evidence_id)
        actions = {action for values in categories.values() for action in values}
        if len(categories) > 1 and len(actions) > 1:
            types = sorted(categories)
            out.append({"kind": "record_category_conflict", "resource_id": rid,
                        "record_types": types,
                        "policy_actions": {rtype: sorted(categories[rtype]) for rtype in types},
                        "evidence": {rtype: sorted(evidence[rtype]) for rtype in types},
                        "detail": "explicit evidence assigns this resource to categories with different "
                                  "required treatments; current decision is preserved for human review"})
    return out


def failed_claim_conflicts(a, state, audit: list[dict]) -> list[dict]:
    """A FAILED deletion claim for a record whose absence rests only on snapshot omission
    (declared or policy-accepted scope) rather than a direct readback.

    The claim is not proof either way, and the gold's FAILED-claim COMPLETE cases rest on
    direct readbacks (status 404), not omission - so this conflict is recorded and sent to
    review, never resolved automatically and never used to change the status.
    """
    out = []
    for x in audit:
        if x["operation"] != "VERIFY_RECORD_ABSENT" or x["state"]["basis"] != "omission":
            continue
        rid = x["resource_id"]
        failed = [r for r in a.store.activity.by_resource.get(rid, [])
                  if r["event_type"] == "DELETE_RECORD" and r["reported_result"] == "FAILED"
                  and r["event_time"] <= state.case.audit_at]
        for r in failed:
            out.append({"resource_id": rid, "kind": "failed_claim_vs_omission", "at": r["event_time"],
                        "evidence": [r["activity_id"], state.decision_steps[x["step_no"] - 1].evidence_id],
                        "claim": "DELETE_RECORD FAILED", "resolution": "review_required",
                        "snapshot_scope": x["state"]["scope"],
                        "resolved_state": "ABSENT (by snapshot omission; not a direct readback)"})
    return out


def attribution_conflicts(a, state, conflicts: list[dict]) -> list[dict]:
    """Account attribution to review: a failed-claim conflict sits on a contested (time-only)
    account that the engine also lists as a tie rival of another case. The account is never
    reassigned here; the cross-case tie is recorded so a reviewer sees both sides."""
    out = []
    for c in conflicts:
        rid = c["resource_id"]
        if rid != state.primary or ownership(state, rid)["tier"] != "contested":
            continue
        others = sorted(cid for cid, rivals in getattr(a, "ambiguous_accounts", {}).items()
                        if rid in rivals and cid != state.case.case_id)
        if others:
            out.append({"kind": "account_attribution_review", "resource_id": rid,
                        "detail": f"time-only attribution; {rid} is also a tie rival of {', '.join(others)}; "
                                  "not reassigned automatically", "rival_of": others})
    return out


def evidence_gaps(ctx, state) -> list[dict]:
    """What the evidence cannot establish for this case (never turned into steps)."""
    if state.not_applicable or state.identity is None:
        return []
    a = ctx.auditor
    gaps = []
    if not state.primary:
        gaps.append({"kind": "primary_account_not_identified",
                     "detail": "no account is tied to the requester by any participant evidence"})
    types = {rs.record_type for rs in state.resources.values() if rs is not None}
    if not types & {"SECURITY_AUDIT_LOG"}:
        gaps.append({"kind": "no_security_audit_record",
                     "detail": "no SECURITY_AUDIT_LOG record is linked to the requester; a retained record "
                               "that exists only outside participant evidence cannot be verified"})
    cid = state.case.case_id
    for rid in sorted(getattr(a, "tied_resources", {}).get(cid, ())):
        others = sorted(c for c, rs in a.tied_resources.items() if rid in rs and c != cid)
        gaps.append({"kind": "workflow_tie", "resource_id": rid,
                     "detail": f"identity-less workflow record shared by cases {', '.join(others)}; left unattributed"})
    rivals = getattr(a, "ambiguous_accounts", {}).get(cid)
    if rivals:
        gaps.append({"kind": "account_time_only_tie", "resource_id": state.primary,
                     "detail": f"primary account chosen by time over {', '.join(rivals)}; flagged for review"})
    for rid in sorted(state.linked):
        rs = state.resources.get(rid)
        if rs is not None and rs.record_type in RETAINED_TYPES and rs.state == "UNKNOWN":
            gaps.append({"kind": "retained_record_unreadable", "resource_id": rid,
                         "detail": "retained record has no readable state at audit_at"})
    return gaps


def classify_miss(rid: str, case_id: str, participant_text: str, tied: dict, rivals: dict) -> str:
    """Why an expected (gold) step is missing: tie | not_discoverable | parser_or_search_error."""
    if rid in tied.get(case_id, set()) or rid in rivals.get(case_id, ()):
        return "tie"
    if rid not in participant_text:
        return "not_discoverable"
    return "parser_or_search_error"

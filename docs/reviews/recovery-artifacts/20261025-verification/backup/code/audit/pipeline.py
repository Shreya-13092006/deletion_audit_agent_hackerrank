"""Sequential audit pipeline.

Parse -> Normalize -> Resolve identity -> Classify intent -> Discover records ->
Resolve state -> Apply policy -> Plan remediation/verification -> Report.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from . import guardrails as g
from .config import CACHE_DIR, STATE_MAX_AGE_DAYS, STATUS_RESULTS, WORKFLOW_WINDOWS, workflow_kind
from .identity import IdentityGraph, email_hash
from .intent import classify
from .aliases import system_for
from .linker import link_resources, visible
from .parsers import load_evidence
from .planner import plan
from .policy import RETAINED_TYPES, Treatment, evaluate, load_rules
from .schema import Case, Decision, Identity
from .state import resolve


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_cases(path: Path) -> list[Case]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [Case(**{k: r[k] for k in Case.__dataclass_fields__}) for r in csv.DictReader(fh)]


class Auditor:
    def __init__(self, dataset_dir: Path, trail, llm=None, store=None):
        self.trail = trail
        self.llm = llm
        self.parser_cap = g.Capability("parser", trail)
        self.planner_cap = g.Capability("planner", trail)
        self.parser_cap.require("read_evidence")
        self.graph = IdentityGraph.load(dataset_dir)
        # `store` lets a caller pass a pre-built EvidenceStore (e.g. rehydrated evidence cards).
        self.store = store if store is not None else load_evidence(dataset_dir, CACHE_DIR / "image_facts.json")
        self.rules = load_rules(dataset_dir)
        self.by_resource: dict[str, list] = {}
        for obs in self.store.observations:
            self.by_resource.setdefault(obs.resource_id, []).append(obs)
        for file_id, err in self.store.errors:
            trail.write("parse_error", file_id=file_id, error=err)
        self.workflow_resources: dict[str, set] = {}
        self.ambiguous_accounts: dict[str, list] = {}

    # ---- identity -------------------------------------------------------------------------
    def identity_for(self, case: Case) -> tuple[Identity, list]:
        users = self.graph.resolve_email(case.email)
        if len(users) == 1:
            return self.graph.identities[users[0]], []
        email = case.email.strip().lower()
        ad_hoc = Identity(user_id=f"unresolved:{email}", emails={email}, hashes={email_hash(email)},
                          phones=set(), names=set())
        if not users:
            return ad_hoc, [g.FLAG_IDENTITY_UNRESOLVED]
        return ad_hoc, [g.FLAG_IDENTITY_AMBIGUOUS]   # never guess between two people

    def links_for(self, ident: Identity, audit_at: str) -> tuple[set, list]:
        """link_resources memoized per (identity identifiers, audit_at); returns fresh copies."""
        memo = self.__dict__.setdefault("_link_memo", {})
        key = (ident.user_id, frozenset(ident.emails), frozenset(ident.hashes), audit_at)
        if key not in memo:
            memo[key] = link_resources(ident, self.store, audit_at, self.by_resource)
        linked, provenance = memo[key]
        return set(linked), list(provenance)

    # ---- workflow attribution (fallback when evidence carries no identity) ----------------
    def assign_workflow_resources(self, cases: list[Case]) -> None:
        """Attribute deletion-workflow activity to the case whose report it produced.

        Deleted accounts and anonymized records keep no identifier, so evidence alone cannot
        tie them to a person. The workflow that produced `reported_status` acted on them in a
        window around `reported_at` (config.WORKFLOW_WINDOWS):
          * the primary-profile DELETE_RECORD runs shortly before the report and its result is
            consistent with the reported status (config.STATUS_RESULTS); matched one-to-one by
            exact status, then evidence co-occurrence, then nearest in time (time-only picks are
            flagged ACCOUNT_WORKFLOW_TIME_ONLY_TIE);
          * other workflow operations go to the single case that reported in the matching window
            and has no evidence-identified record of that system already;
          * for those other operations, ties between cases are broken only by evidence co-occurrence (a file at or before the
            case's audit_at that reads both the candidate and the case's identified records);
            a tie that evidence cannot break stays unattributed - never a guess between people.
        Resources already tied to a person by evidence are never re-attributed.
        """
        claimed: set = set()
        case_linked: dict[str, set] = {}
        for case in cases:
            ident, _ = self.identity_for(case)
            linked, _ = self.links_for(ident, case.audit_at)
            claimed |= linked
            case_linked[case.case_id] = linked
        evidence_accounts = {cid: any(r.startswith("account_") for r in linked)
                             for cid, linked in case_linked.items()}

        def cooccurrence(case: Case, rid: str) -> int:
            """Evidence files visible at audit_at that read both `rid` and the case's records."""
            files = {o.evidence_id for o in self.by_resource.get(rid, [])
                     if o.evidence_id in self.store.manifest and visible(o, case.audit_at)}
            mine = {o.evidence_id for r in case_linked[case.case_id] for o in self.by_resource.get(r, [])
                    if o.evidence_id in self.store.manifest and visible(o, case.audit_at)}
            return len(files & mine)
        # Any resource carrying a known person's identifier belongs to that person.
        for obs in self.store.observations:
            if obs.state != "LINK" and self.graph.users_for(obs.emails, obs.hashes, obs.users):
                claimed.add(obs.resource_id)

        # Candidate accounts per case, keyed by (status-consistency rank, -evidence support).
        candidates: dict[str, dict[str, tuple]] = {}
        lo, hi = WORKFLOW_WINDOWS["account"]
        for case in cases:
            if evidence_accounts[case.case_id]:
                continue
            rep = _ts(case.reported_at)
            allowed = STATUS_RESULTS.get(case.reported_status, ())
            for row in self.store.activity.account_deletes:
                if row["resource_id"] in claimed or row["event_time"] > case.audit_at:
                    continue
                gap = (_ts(row["event_time"]) - rep).total_seconds() / 3600
                if lo <= gap <= hi and row["reported_result"] in allowed:
                    key = (allowed.index(row["reported_result"]), -cooccurrence(case, row["resource_id"]))
                    candidates.setdefault(case.case_id, {})[row["resource_id"]] = (key, row["activity_id"], gap)
        # Greedy one-to-one match: status consistency, then evidence support, then time proximity
        # (82% correct on the public samples). A pick decided by time alone - another open
        # candidate had the same status and support - is flagged as a tie for review.
        pairs = sorted((key, abs(gap), cid, acc, act)
                       for cid, cands in candidates.items() for acc, (key, act, gap) in cands.items())
        used_cases, used_accounts = set(), set()
        for key, gap, cid, acc, act in pairs:
            if cid in used_cases or acc in used_accounts:
                continue
            rivals = [a for a, (k, _, _) in candidates[cid].items()
                      if a != acc and a not in used_accounts and k == key]
            used_cases.add(cid)
            used_accounts.add(acc)
            self.workflow_resources.setdefault(cid, set()).add(acc)
            if rivals:
                self.ambiguous_accounts[cid] = sorted(rivals)
            self.trail.write("workflow_attribution", case_id=cid, resource_id=acc, activity_id=act,
                             gap_hours=round(gap, 2), kind="account", evidence_support=-key[1],
                             time_only_tie_with=sorted(rivals))

        windows = [(c, _ts(c.reported_at)) for c in cases]
        for row in self.store.activity.rows:
            rid = row["resource_id"]
            kind = workflow_kind(row)
            if kind is None or rid.startswith("account_") or rid in claimed:
                continue
            lo, hi = WORKFLOW_WINDOWS[kind]
            t = _ts(row["event_time"])
            system = system_for(rid)
            owners = [c for c, rep in windows
                      if lo <= (t - rep).total_seconds() / 3600 <= hi and row["event_time"] <= c.audit_at
                      and not any(system_for(r) == system for r in case_linked[c.case_id])]
            if len(owners) > 1:
                scores = sorted(((cooccurrence(c, rid), c.case_id) for c in owners), reverse=True)
                if scores[0][0] > 0 and scores[0][0] > scores[1][0]:
                    owners = [c for c in owners if c.case_id == scores[0][1]]
            if len(owners) == 1:
                self.workflow_resources.setdefault(owners[0].case_id, set()).add(rid)
                self.trail.write("workflow_attribution", case_id=owners[0].case_id, resource_id=rid,
                                 activity_id=row["activity_id"], kind=kind)

    def primary_account(self, case: Case, linked: set) -> str | None:
        """The profile the deletion workflow acted on for this report, else the latest seen."""
        accounts = sorted(r for r in linked if r.startswith("account_"))
        if not accounts:
            return None
        rep = _ts(case.reported_at)
        lo, hi = WORKFLOW_WINDOWS["account"]
        for acc in accounts:
            for row in self.store.activity.by_resource.get(acc, []):
                if row["event_type"] == "DELETE_RECORD" and \
                        lo <= (_ts(row["event_time"]) - rep).total_seconds() / 3600 <= hi:
                    return acc
        for acc in accounts:
            if acc in self.workflow_resources.get(case.case_id, set()):
                return acc
        seen = [(max((o.observed_at for o in self.by_resource.get(a, [])), default=""), a) for a in accounts]
        return max(seen)[1]

    # ---- one case: reusable steps (shared with the agent tools in audit/agent) ------------
    def intent_for(self, case: Case, linked: set) -> tuple[bool, list, str]:
        """classify() with the CLASSIFY_REQUEST corroboration for the subject's records."""
        non_deletion = any(
            row["event_time"] <= case.audit_at
            for rid in linked for row in [self.store.activity.non_deletion_resources.get(rid)] if row)
        return classify(case.request_text, non_deletion, self.llm)

    def attribute(self, case: Case, linked: set, flags: list) -> tuple[set, set, str | None]:
        """Add workflow-attributed resources (flagged) and pick the primary profile."""
        attributed = self.workflow_resources.get(case.case_id, set()) - linked
        if attributed:
            linked |= attributed
            flags.append(g.FLAG_ACCOUNT_INFERRED)
        primary = self.primary_account(case, linked)
        if primary is None:
            flags.append(g.FLAG_ACCOUNT_UNKNOWN)
        elif case.case_id in self.ambiguous_accounts and primary in attributed:
            flags.append(g.FLAG_ACCOUNT_TIE)
        return linked, attributed, primary

    def resolve_state(self, case: Case, rid: str):
        return resolve(rid, self.by_resource.get(rid, []), self.store.covers, case.audit_at,
                       STATE_MAX_AGE_DAYS)

    def treat(self, rid: str, rs, primary: str | None, flags: list):
        """Policy treatment of one resolved resource -> (rs, Treatment) or None."""
        if rs.state == "UNKNOWN":
            if rid == primary:
                # The subject's profile must end absent; without a readable state at
                # audit_at it can only be a post-remediation check.
                flags.append(f"{g.FLAG_STATE_UNKNOWN}:{rid}")
                return rs, Treatment(None, None, "VERIFY_RECORD_ABSENT", "", future_only=True)
            if rs.record_type in RETAINED_TYPES:
                # Policy-retained record known only from later evidence: it can still be a
                # post-remediation check, but never a cited COMPLETE verification.
                flags.append(f"{g.FLAG_RETAINED_LATER_EVIDENCE}:{rid}")
                return rs, Treatment(None, None, "VERIFY_RECORD_PRESENT", "", future_only=True)
            flags.append(f"{g.FLAG_STATE_UNKNOWN}:{rid}")
            return None
        if str(rs.attrs.get("note", "")).startswith("contact not in identity tables"):
            # The record is tied to the subject by a catalog link but displays a contact that
            # is not theirs: keep the evidence-backed treatment, surface the conflict.
            flags.append(f"{g.FLAG_CONTACT_CONFLICT}:{rid}")
        treatment = evaluate(rs, self.rules)
        if treatment is None:
            return None
        if treatment.finding is None and treatment.verification == "VERIFY_RECORD_ABSENT" \
                and rid != primary:
            return None     # already-deleted copies other than the primary profile need no check
        return rs, treatment

    @staticmethod
    def finalize(items: list, flags: list) -> tuple[str, list]:
        status, steps = plan(items)
        if status == "COMPLETE" and not steps:
            # Fail safe: nothing citable proves the required state at audit_at, so completion
            # cannot be claimed. Report the checks that must pass instead.
            status, steps = plan(items, force_incomplete=True)
            flags.append(g.FLAG_NO_PROOF)
        return status, steps

    # ---- one case ------------------------------------------------------------------------
    def audit(self, case: Case) -> Decision:
        ident, flags = self.identity_for(case)
        linked, provenance = self.links_for(ident, case.audit_at)
        authorized, intent_flags, reason = self.intent_for(case, linked)
        flags += intent_flags
        self.trail.write("intent", case_id=case.case_id, authorized=authorized, reason=reason)
        if not authorized:
            return Decision(case.case_id, "NOT_APPLICABLE", [], flags, [reason])

        linked, _attributed, primary = self.attribute(case, linked, flags)
        self.planner_cap.require("propose_remediation")
        items = []
        for rid in sorted(linked):
            item = self.treat(rid, self.resolve_state(case, rid), primary, flags)
            if item is not None:
                items.append(item)
        status, steps = self.finalize(items, flags)
        self.trail.write("decision", case_id=case.case_id, status=status, user=ident.user_id,
                         resources=sorted(linked), flags=flags,
                         provenance=[list(p) for p in provenance])
        return Decision(case.case_id, status, steps, flags)

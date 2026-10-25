"""Resolve each resource's state at audit_at from its timeline of observations.

  * only observations at or before audit_at count (linker.visible), and only recent ones:
    a reading older than config.STATE_MAX_AGE_DAYS does not establish the state at audit_at
  * a snapshot proves absence only for systems in its scope (ScopeCover)
  * at one point in time, any copy (primary or replica) showing the record means PRESENT
  * the latest point in time decides existence; the latest non-null reading decides PII
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .aliases import record_type_for, system_for
from .linker import visible
from .schema import ABSENT, ACTIVE, BLOCKED, DISABLED, PRESENT, Observation

SPECIFIC_TYPES = ("SUPPORT_ATTACHMENT", "MARKETING_PROFILE", "SECONDARY_IDENTIFIER",
                  "EMAIL_DELIVERY_LOG", "PRODUCT_TELEMETRY", "CACHE_ENTRY")
DOMINANCE = {ACTIVE: 3, PRESENT: 2, BLOCKED: 1, DISABLED: 1, ABSENT: 0}


@dataclass
class Fact:
    at: str
    state: str
    evidence_id: str
    pii: bool | None = None
    record_type: str | None = None


@dataclass
class ResourceState:
    resource_id: str
    system_id: str
    record_type: str | None
    state: str                      # PRESENT / ABSENT / ACTIVE / DISABLED / BLOCKED / UNKNOWN
    pii: bool | None
    evidence_id: str                # file/activity proving `state`
    pii_evidence_id: str = ""
    facts: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)


def horizon_start(audit_at: str, days: float) -> str:
    start = datetime.fromisoformat(audit_at.replace("Z", "+00:00")) - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve(resource_id: str, observations: list[Observation], covers: list, audit_at: str,
            max_age_days: float | None = None) -> ResourceState:
    system = system_for(resource_id)
    facts: list[Fact] = []
    attrs: dict = {}
    oldest = horizon_start(audit_at, max_age_days) if max_age_days else ""
    for obs in observations:
        if obs.state == "LINK" or not visible(obs, audit_at) or obs.observed_at < oldest:
            continue
        facts.append(Fact(obs.observed_at, obs.state, obs.evidence_id, obs.pii, obs.record_type))
        attrs.update({k: v for k, v in obs.attrs.items() if v not in (None, "")})
    if not facts and not any(o.state != "LINK" for o in observations):
        # Absence by omission is weaker than any explicit reading: snapshot bundles hold only
        # the records captured for their subjects, so they decide state only for resources that
        # no evidence ever observed directly (e.g. a deleted primary profile). A resource seen
        # only in later evidence stays UNKNOWN at audit_at rather than "absent".
        omitted = [c for c in covers if c.system_id == system and oldest <= c.captured_at <= audit_at
                   and resource_id not in c.resource_ids]
        if omitted:
            latest = max(omitted, key=lambda c: (c.captured_at, c.evidence_id))
            facts.append(Fact(latest.captured_at, ABSENT, latest.evidence_id))

    rtype = _record_type(facts, resource_id) or _record_type(
        [Fact(o.observed_at, o.state, o.evidence_id, None, o.record_type) for o in observations], resource_id)
    if not facts:
        return ResourceState(resource_id, system, rtype, "UNKNOWN", None, "", facts=facts, attrs=attrs)

    latest_at = max(f.at for f in facts)
    latest = [f for f in facts if f.at == latest_at]
    top = max(latest, key=lambda f: (DOMINANCE.get(f.state, 0), f.evidence_id))
    pii_facts = sorted((f for f in facts if f.pii is not None), key=lambda f: (f.at, f.pii))
    pii = pii_facts[-1].pii if pii_facts else None
    pii_ev = pii_facts[-1].evidence_id if pii_facts else ""
    return ResourceState(resource_id, system, rtype, top.state, pii, top.evidence_id, pii_ev,
                         facts=sorted(facts, key=lambda f: f.at), attrs=attrs)


def _record_type(facts: list[Fact], resource_id: str) -> str | None:
    types = [f.record_type for f in facts if f.record_type]
    for special in SPECIFIC_TYPES:
        if special in types:
            return special
    return types[-1] if types else record_type_for(resource_id)

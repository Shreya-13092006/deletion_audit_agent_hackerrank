"""Link observations to one deletion subject using exact identifiers and resource links.

Rules (dataset-specific, see docs/dataset-observations.md):
  * match on normalized email, sha256 email hash (current or historical) or user_id; never names
  * a record naming a *different* user_id is a decoy and is not linked through email alone
  * once a resource is linked, all of its observations are in scope (resource propagation)
  * search documents link to their `source_resource_id` account
  * a connector/backup that repopulated a linked resource is itself linked (recreation path)
  * ownership (who a resource belongs to) is time-invariant, so it may come from any
    evidence; the resource's *state* and every citation still use only evidence available
    at or before `audit_at` (see state.py). Links found only in later evidence are tagged.
"""
from __future__ import annotations

from .schema import Identity, Observation


def visible(obs: Observation, audit_at: str) -> bool:
    return obs.observed_at <= audit_at and obs.captured_at <= audit_at


def matches(obs: Observation, ident: Identity) -> bool:
    if obs.users and ident.user_id not in obs.users:
        return False                                    # names another subject: decoy
    return bool(obs.emails & ident.emails or obs.hashes & ident.hashes or ident.user_id in obs.users)


def _identifier_index(store) -> dict:
    """identifier -> sorted store positions of observations carrying it (built once per store).

    Only an observation sharing an email, hash or user_id with the subject can satisfy
    `matches`, so the index narrows the scan without changing which observations match.
    The cache is rebuilt if the observation list is replaced or grows.
    """
    observations = store.observations
    cached = getattr(store, "_linker_index", None)
    if cached is not None and cached[0] is observations and cached[1] == len(observations):
        return cached[2]
    index: dict = {}
    for pos, obs in enumerate(observations):
        for key in {("e", v) for v in obs.emails} | {("h", v) for v in obs.hashes} | \
                {("u", v) for v in obs.users}:
            index.setdefault(key, []).append(pos)
    store._linker_index = (observations, len(observations), index)
    return index


def link_resources(ident: Identity, store, audit_at: str, by_resource: dict) -> tuple[set, list]:
    """Return (linked resource ids, provenance list of (resource, reason, evidence_id))."""
    linked: dict[str, tuple] = {}
    index = _identifier_index(store)
    observations = store.observations
    positions: set = set()
    for key in [("e", v) for v in ident.emails] + [("h", v) for v in ident.hashes] + [("u", ident.user_id)]:
        positions.update(index.get(key, ()))
    # Same order as a stable sort of all observations on `not visible`: visible first, each
    # group in store order, so the first match per resource (and its provenance) is unchanged.
    candidates = sorted(positions, key=lambda p: (not visible(observations[p], audit_at), p))
    for obs in (observations[p] for p in candidates):
        if matches(obs, ident) and obs.resource_id not in linked:
            reason = "identifier" if visible(obs, audit_at) else "identifier_later_evidence"
            linked[obs.resource_id] = (obs.resource_id, reason, obs.evidence_id)

    changed = True
    while changed:
        changed = False
        for a, b, ev in store.links:                    # search doc <-> source account
            if ev in store.manifest and store.manifest[ev]["captured_at"] > audit_at:
                continue
            for x, y in ((a, b), (b, a)):
                if x in linked and y not in linked and _no_conflict(y, ident, by_resource, audit_at):
                    linked[y] = (y, f"resource_link:{x}", ev)
                    changed = True
        for source, downstream, row in store.activity.recreation_links:
            if row["event_time"] <= audit_at and downstream in linked and source not in linked:
                linked[source] = (source, f"repopulates:{downstream}", row["activity_id"])
                changed = True
    return set(linked), list(linked.values())


def _no_conflict(rid: str, ident: Identity, by_resource: dict, audit_at: str) -> bool:
    """A propagated resource must not carry identifiers of another person."""
    for obs in by_resource.get(rid, []):
        if visible(obs, audit_at) and obs.users and ident.user_id not in obs.users:
            return False
    return True

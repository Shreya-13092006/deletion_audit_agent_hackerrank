"""Shared fixtures for the regression tests."""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from audit import config  # noqa: E402
from audit.identity import IdentityGraph, email_hash  # noqa: E402
from audit.schema import Identity, Observation, ScopeCover  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402


def obs(rid, state="PRESENT", at="2026-09-01T00:00:00Z", ev="evidence_x", **kw):
    from audit.aliases import record_type_for, system_for
    return Observation(evidence_id=ev, observed_at=at, captured_at=kw.pop("captured_at", at),
                       system_id=system_for(rid), resource_id=rid,
                       record_type=kw.pop("record_type", record_type_for(rid)), state=state, **kw)


def ident(user="user_1", emails=("a@x.com",)):
    emails = {e.lower() for e in emails}
    return Identity(user, emails, {email_hash(e) for e in emails}, set(), set())


class FakeActivity:
    recreation_links: list = []
    rows: list = []


class FakeStore:
    def __init__(self, observations, links=(), covers=(), recreation=()):
        self.observations = list(observations)
        self.links = list(links)
        self.covers = list(covers)
        self.manifest = {}
        self.activity = FakeActivity()
        self.activity.recreation_links = list(recreation)


@lru_cache(maxsize=1)
def real_graph() -> IdentityGraph:
    return IdentityGraph.load(config.DATASET_DIR)


@lru_cache(maxsize=1)
def real_auditor():
    from audit.pipeline import Auditor, load_cases
    auditor = Auditor(config.DATASET_DIR, AuditTrail(None))
    cases = load_cases(config.DATASET_DIR / "deletion_requests.csv") + \
        load_cases(config.DATASET_DIR / "sample_deletion_requests.csv")
    auditor.assign_workflow_resources(cases)
    return auditor, {c.case_id: c for c in cases}


__all__ = ["obs", "ident", "FakeStore", "ScopeCover", "real_graph", "real_auditor", "email_hash"]

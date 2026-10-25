"""Canonical data structures shared by every pipeline stage."""
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical observation states.
PRESENT, ABSENT = "PRESENT", "ABSENT"
ACTIVE, DISABLED, BLOCKED = "ACTIVE", "DISABLED", "BLOCKED"


@dataclass
class Observation:
    """One evidence-backed fact about one resource at one point in time (the "evidence card").

    `pii` is True when direct identifiers are still visible on the record, False when the
    evidence shows them removed (redacted/anonymized), and None when the source says nothing.
    """
    evidence_id: str            # file_id, activity_id or audit_id
    observed_at: str            # ISO-8601 UTC; row-level time when the source has one
    captured_at: str            # when the evidence file itself was captured
    system_id: str
    resource_id: str
    record_type: str | None     # deletion_rules.data_category, DATA_FLOW or None
    state: str                  # PRESENT / ABSENT / ACTIVE / DISABLED / BLOCKED
    pii: bool | None = None
    emails: set = field(default_factory=set)    # normalized (trimmed, lowercased)
    hashes: set = field(default_factory=set)    # 64-hex lowercase
    users: set = field(default_factory=set)     # user_N
    phones: set = field(default_factory=set)
    source: str = ""            # parser/table/collection that produced it (provenance)
    replica: str = ""           # replica/table name for primary-vs-replica comparisons
    attrs: dict = field(default_factory=dict)   # original field values kept for audit

    @property
    def identifiers(self) -> set:
        return self.emails | self.hashes | self.users


@dataclass
class ScopeCover:
    """A snapshot that covered `system_id` at `captured_at`: absence there proves absence."""
    evidence_id: str
    captured_at: str
    system_id: str
    resource_ids: frozenset     # every resource of that system present in the snapshot
    record_type: str | None = None


@dataclass
class Identity:
    user_id: str
    emails: set
    hashes: set
    phones: set
    names: set                  # kept for provenance only; never used for linking

    @property
    def identifiers(self) -> set:
        return self.emails | self.hashes | {self.user_id}


@dataclass
class Case:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass(frozen=True)
class Step:
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str = ""


@dataclass
class Decision:
    case_id: str
    status: str                 # COMPLETE / INCOMPLETE / NOT_APPLICABLE
    steps: list
    flags: list = field(default_factory=list)   # fail-safe / uncertainty markers
    notes: list = field(default_factory=list)

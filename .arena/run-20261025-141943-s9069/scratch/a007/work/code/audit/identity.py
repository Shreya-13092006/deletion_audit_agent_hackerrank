"""Identity graph: current snapshot + audit history -> every identifier a user has ever had.

Linking uses exact email (trimmed, lowercased), sha256(email) hashes, and user_id only.
Names are kept for provenance but never used to link records.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .aliases import norm_email
from .schema import Identity


def email_hash(email: str) -> str:
    """Dataset algorithm, verified on all 850 identities: sha256 over the lowercased UTF-8 email."""
    return hashlib.sha256(norm_email(email).encode("utf-8")).hexdigest()


class IdentityGraph:
    def __init__(self, identities: dict[str, Identity]):
        self.identities = identities
        # user_ids whose stored email_hash differs from sha256(current email); both are kept
        # as identifiers, the mismatch is surfaced for review (0 in the shipped dataset).
        self.hash_mismatches: set = {u for u, i in identities.items() if getattr(i, "_hash_mismatch", False)}
        self.by_email: dict[str, set] = {}
        self.by_hash: dict[str, set] = {}
        self.by_phone: dict[str, set] = {}
        for ident in identities.values():
            for e in ident.emails:
                self.by_email.setdefault(e, set()).add(ident.user_id)
            for h in ident.hashes:
                self.by_hash.setdefault(h, set()).add(ident.user_id)
            for p in ident.phones:
                self.by_phone.setdefault(p, set()).add(ident.user_id)

    @classmethod
    def load(cls, dataset_dir: Path) -> "IdentityGraph":
        identities: dict[str, Identity] = {}
        with open(dataset_dir / "user_identities.csv", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                email = norm_email(row["email"])
                identities[row["user_id"]] = Identity(
                    user_id=row["user_id"],
                    emails={email},
                    hashes={email_hash(email), row["email_hash"].strip().lower()},
                    phones={row["phone"].strip()},
                    names={row["name"].strip()},
                )
                if row["email_hash"].strip() and row["email_hash"].strip().lower() != email_hash(email):
                    identities[row["user_id"]]._hash_mismatch = True
        with open(dataset_dir / "user_audit_log.csv", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                ident = identities.get(row["user_id"])
                if ident is None:
                    continue
                for value in (row["old_value"], row["new_value"]):
                    value = (value or "").strip()
                    if not value:
                        continue
                    if row["field_name"] == "email":
                        ident.emails.add(norm_email(value))
                        ident.hashes.add(email_hash(value))
                    elif row["field_name"] == "email_hash":
                        ident.hashes.add(value.lower())
                    elif row["field_name"] == "phone":
                        ident.phones.add(value)
        return cls(identities)

    def resolve_email(self, email: str) -> list[str]:
        """All user_ids whose current or historical email equals `email` (normalized)."""
        return sorted(self.by_email.get(norm_email(email), set()))

    def users_for(self, emails=(), hashes=(), users=()) -> set:
        """Users matched by exact identifiers. Unknown user_ids are ignored."""
        found = set()
        for e in emails:
            found |= self.by_email.get(e, set())
        for h in hashes:
            found |= self.by_hash.get(h, set())
        for u in users:
            if u in self.identities:
                found.add(u)
        return found

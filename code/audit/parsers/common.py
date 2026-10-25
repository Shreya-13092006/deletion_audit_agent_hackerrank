"""Shared record -> Observation conversion used by every structured parser."""
from __future__ import annotations

from ..aliases import (NULLS, emails_in_text, extract_identifiers, has_direct_identifiers,
                       record_type_for, system_for)
from ..schema import ABSENT, ACTIVE, BLOCKED, DISABLED, PRESENT, Observation

# Generic ledger "result" vocabulary -> (state, pii).
RESULT_STATE = {
    "FOUND": (PRESENT, None),
    "NOT_FOUND": (ABSENT, None),
    "IDENTIFIABLE": (PRESENT, True),
    "ANONYMIZED": (PRESENT, False),
    "REDACTED": (PRESENT, False),
    "ACTIVE": (ACTIVE, None),
    "DISABLED": (DISABLED, None),
    "BLOCKED": (BLOCKED, None),
}


def truthy(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in NULLS:
        return None
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "enabled"}:
        return True
    if s in {"false", "0", "no", "disabled"}:
        return False
    return None


def flatten(record: dict) -> dict:
    """Merge nested `document` / `profile` dicts into one flat field map (outer keys win)."""
    flat = {}
    for key in ("document", "profile"):
        inner = record.get(key)
        if isinstance(inner, dict):
            flat.update(inner)
    for key, value in record.items():
        if not isinstance(value, (dict, list)):
            flat[key] = value
    return flat


def record_observation(record: dict, *, evidence_id: str, observed_at: str, captured_at: str,
                       collection: str | None, source: str, replica: str = "",
                       system_hint: str | None = None) -> Observation | None:
    """Convert one structured record (SQL row, JSON record, ledger row) into an Observation."""
    rid = str(record.get("resource_id") or "").strip()
    if not rid:
        return None
    flat = flatten(record)
    ids = extract_identifiers(flat)
    system = system_for(rid) or system_hint or ""
    rtype = flat.get("record_type") or record_type_for(rid, collection)
    state, pii = PRESENT, has_direct_identifiers(flat)

    # Message bodies: an embedded email is still exposed personal data.
    text = flat.get("message_text") or flat.get("message_excerpt")
    if isinstance(text, str):
        found = emails_in_text(text)
        ids["emails"] |= found
        if found:
            pii = True
        elif text.strip() == "[REDACTED]":
            pii = False if pii is not True else pii

    if "result" in flat and str(flat["result"]).upper() in RESULT_STATE:
        state, result_pii = RESULT_STATE[str(flat["result"]).upper()]
        if result_pii is not None:
            pii = result_pii
        if rtype == "BACKUP_ARCHIVE" and state == ACTIVE:
            state = ACTIVE          # restore path still open
    if "enabled" in flat and truthy(flat["enabled"]) is not None:
        state = ACTIVE if truthy(flat["enabled"]) else DISABLED
        rtype = rtype or "DATA_FLOW"
    if "restore_allowed" in flat and truthy(flat["restore_allowed"]) is not None:
        state = ACTIVE if truthy(flat["restore_allowed"]) else BLOCKED
    if "status_code" in flat:
        state = PRESENT if str(flat["status_code"]) == "200" else ABSENT
    if rtype in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY") and pii is not True:
        # Still attributable when it carries a stable user reference.
        if any(flat.get(k) not in NULLS for k in ("user_id", "customer_reference") if k in flat):
            pii = True
    if rtype == "ACCOUNT_TOMBSTONE":
        state = PRESENT
    if rtype == "USER_PROFILE" and str(flat.get("account_status", "")).upper() == "DELETED":
        state = ABSENT

    return Observation(
        evidence_id=evidence_id, observed_at=observed_at, captured_at=captured_at,
        system_id=system, resource_id=rid, record_type=rtype, state=state, pii=pii,
        emails=ids["emails"], hashes=ids["hashes"], users=ids["users"], phones=ids["phones"],
        source=source, replica=replica,
        attrs={k: v for k, v in flat.items() if k != "resource_id"},
    )

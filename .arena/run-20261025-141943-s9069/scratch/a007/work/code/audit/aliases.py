"""Alias map: every documented field/value variant mapped to canonical identifiers.

Identifier values are only *classified* here (email / user_id / hash / phone). Whether a value
belongs to a deletion subject is decided later by an exact lookup in the identity graph.
"""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
USER_RE = re.compile(r"^user_\d+$")
HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RESOURCE_RE = re.compile(
    r"\b(account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|legal_hold|"
    r"marketing|email_delivery|cache|object)_\d+\b")

# Fields whose value identifies a person (any of email / user_id / hash).
IDENTITY_FIELDS = {
    "user_id", "customer_reference", "subject_reference", "subject_ref", "subject_selector",
    "email", "owner_email", "requester_email", "customer_email", "uploaded_by", "account",
    "lookup_key", "match_key", "subject_key", "scan_key", "matched_value", "lookup_value",
    "correlation_key", "email_hash", "query",
}
PHONE_FIELDS = {"phone", "owner_phone", "requester_phone"}
NAME_FIELDS = {"full_name", "name", "display_name", "requester_name"}
# Direct identifiers whose presence means personal data is still exposed on a retained record.
DIRECT_ID_FIELDS = {"full_name", "name", "display_name", "requester_name", "email", "owner_email",
                    "requester_email", "customer_email", "phone", "owner_phone", "requester_phone",
                    "email_hash"}

PREFIX_SYSTEM = {
    "account": "account_service", "search": "search_service", "analytics": "analytics_platform",
    "support": "support_platform", "export": "export_service", "data_flow": "integration_service",
    "backup": "backup_service", "audit_record": "security_service", "tombstone": "identity_service",
    "legal_hold": "legal_service", "marketing": "marketing_platform",
    "email_delivery": "email_delivery_service", "cache": "cache_service", "object": "object_storage",
}

PREFIX_RECORD_TYPE = {
    "account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "analytics": "ANALYTICS_PROFILE",
    "support": "SUPPORT_MESSAGE", "export": "USER_EXPORT", "data_flow": "DATA_FLOW",
    "backup": "BACKUP_ARCHIVE", "audit_record": "SECURITY_AUDIT_LOG", "tombstone": "ACCOUNT_TOMBSTONE",
    "legal_hold": "LEGAL_HOLD_RECORD", "marketing": "MARKETING_PROFILE",
    "email_delivery": "EMAIL_DELIVERY_LOG", "cache": "CACHE_ENTRY", "object": "SUPPORT_ATTACHMENT",
}

# Table / collection names -> record_type (deletion_rules.data_category).
COLLECTION_RECORD_TYPE = {
    "customer_profiles": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "search_documents_primary": "SEARCH_INDEX_ENTRY",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "support_records": "SUPPORT_MESSAGE",
    "support_conversations": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "customer_exports": "USER_EXPORT",
    "customer_export_jobs": "USER_EXPORT",
    "connector_subscriptions": "DATA_FLOW",
    "connector_configurations": "DATA_FLOW",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "backup_catalog": "BACKUP_ARCHIVE",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
}

NULLS = {None, "", "null", "none", "None", "NULL"}


def norm_email(value: str) -> str:
    return value.strip().lower()


def resource_prefix(resource_id: str) -> str:
    m = re.match(r"^(.*)_\d+$", resource_id or "")
    return m.group(1) if m else ""


def system_for(resource_id: str) -> str:
    return PREFIX_SYSTEM.get(resource_prefix(resource_id), "")


def record_type_for(resource_id: str, collection: str | None = None) -> str | None:
    if collection and collection in COLLECTION_RECORD_TYPE:
        return COLLECTION_RECORD_TYPE[collection]
    return PREFIX_RECORD_TYPE.get(resource_prefix(resource_id))


def classify_value(value) -> tuple[str, str] | None:
    """Return ('email'|'user'|'hash', canonical) for an identifier-looking value, else None."""
    if value in NULLS or not isinstance(value, str):
        return None
    v = value.strip().strip('"')
    if USER_RE.match(v):
        return ("user", v)
    if HASH_RE.match(v):
        return ("hash", v.lower())
    if "@" in v and EMAIL_RE.fullmatch(v):
        return ("email", norm_email(v))
    return None


def extract_identifiers(fields: dict) -> dict:
    """Collect canonical identifiers from known identity fields of a flat record."""
    out = {"emails": set(), "users": set(), "hashes": set(), "phones": set()}
    for key, value in fields.items():
        if key in IDENTITY_FIELDS:
            hit = classify_value(value)
            if hit:
                out[{"email": "emails", "user": "users", "hash": "hashes"}[hit[0]]].add(hit[1])
        elif key in PHONE_FIELDS and value not in NULLS:
            out["phones"].add(str(value).strip())
    return out


def emails_in_text(text: str) -> set:
    """Controlled free-text extraction; callers must still validate against the identity graph."""
    return {norm_email(m) for m in EMAIL_RE.findall(text or "")}


def has_direct_identifiers(fields: dict) -> bool | None:
    """True if any direct-identifier field holds a value, False if all known ones are null."""
    seen = False
    for key in DIRECT_ID_FIELDS:
        if key in fields:
            seen = True
            if fields[key] not in NULLS and fields[key] != "[REDACTED]":
                return True
    return False if seen else None

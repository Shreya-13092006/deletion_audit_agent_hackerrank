"""Log files (seven line formats) -> events -> Observations.

Formats: logfmt, JSON-after-timestamp, RFC5424 syslog, "[LEVEL] [service] [trace] event:",
"| LEVEL | service | trace | event |", "requestId=... function=... message=\"...\"" and the
plain `record_lookup` ledger. Identity keys usually sit on a `*_started` line while the
resource and outcome sit on the `*_completed` line; both are joined by trace_id.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..aliases import NULLS, classify_value, extract_identifiers, record_type_for, system_for
from ..schema import ABSENT, ACTIVE, BLOCKED, DISABLED, PRESENT, Observation
from .common import RESULT_STATE, truthy

TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+(.*)$")
KV_RE = re.compile(r'([A-Za-z_][\w.]*)=("(?:[^"\\]|\\.)*"|\S+)')
BRACKET_RE = re.compile(r"^\[(\w+)\]\s+\[([\w.-]+)\]\s+\[([\w.-]+)\]\s+(\w+):\s*(.*)$")
PIPE_RE = re.compile(r"^\|\s*(\w+)\s*\|\s*([\w.-]+)\s*\|\s*([\w.-]+)\s*\|\s*(\w+)\s*\|\s*(.*)$")
SYSLOG_RE = re.compile(r"^<\d+>\d+\s+\S+\s+([\w.-]+)\s+([\w.-]+)\s+-\s+-\s+(.*)$")

# Infrastructure noise with no bearing on any person's data.
NOISE_SERVICES = {"dns_cache", "secret_agent", "queue_consumer", "webhook_delivery", "feature_flags",
                  "circuit_breaker", "log_router", "checkpoint_writer", "readback_collector",
                  "attachment_preview", "scheduler", "metrics_agent", "tls_monitor", "disk_monitor"}


def _kv(text: str) -> dict:
    out = {}
    for key, value in KV_RE.findall(text):
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"')
        out[key] = value
    msg = out.get("message")
    if msg and "=" in msg:                               # requestId format nests kv in message
        out.update(_kv(msg))
    return out


def parse_line(line: str) -> dict | None:
    m = TS_RE.match(line.strip())
    if not m:
        return None
    ts, rest = m.groups()
    ev = {"ts": ts}
    if rest.startswith("{"):
        try:
            ev.update(json.loads(rest))
        except json.JSONDecodeError:
            return None
    elif (b := BRACKET_RE.match(rest)):
        ev.update(level=b[1], service=b[2], trace_id=b[3], event=b[4])
        ev.update(_kv(b[5]))
    elif (p := PIPE_RE.match(rest)):
        ev.update(level=p[1], service=p[2], trace_id=p[3], event=p[4])
        ev.update(_kv(p[5]))
    elif (s := SYSLOG_RE.match(rest)):
        ev.update(service=s[1], trace_id=s[2])
        ev.update(_kv(s[3]))
    else:
        ev.update(_kv(rest))
        if "requestId" in ev:
            ev.setdefault("trace_id", ev["requestId"])
        if "function" in ev:
            ev.setdefault("service", ev["function"])
    ev.setdefault("service", ev.get("logger", ""))
    return ev


def _event_state(ev: dict):
    """(state, pii, record_type) implied by a completed/scan event, or None if uninformative."""
    name = ev.get("event", "")
    rid = ev.get("resource_id", "")
    if name == "record_lookup":
        state, pii = RESULT_STATE.get(str(ev.get("result", "")).upper(), (None, None))
        return (state, pii, ev.get("record_type")) if state else None
    if name in {"profile_lookup_completed", "contact_query_completed", "audit_record_read_completed",
                "contact_lookup_completed"}:
        rows = ev.get("rows")
        status = ev.get("http_status")
        present = _lookup_presence(rows, status)
        if present is None:
            return None
        rtype = None
        if name == "contact_lookup_completed":
            rtype = "MARKETING_PROFILE"     # contact/opt-in record keyed by identifier
        elif name == "contact_query_completed":
            rtype = "SECONDARY_IDENTIFIER"  # legacy contact-index copy, not a conversation
        return (PRESENT if present else ABSENT, None, rtype)
    if name == "index_query_completed":
        return (PRESENT if ev.get("result") == "hit" else ABSENT, None, None)
    if name in {"message_pii_scan", "analytics_identity_scan"}:
        return (PRESENT, True, None)
    if name == "attachment_pii_scan":
        return (PRESENT, True, "SUPPORT_ATTACHMENT")
    if name == "deletion_marker_check":
        return (PRESENT, None, "SECONDARY_IDENTIFIER") if ev.get("marker_found") == "false" else None
    if name in {"analytics_profile_read", "analytics_profile_read_completed",
                "support_ticket_read_completed", "message_read"}:
        fields = {k: ev.get(k) for k in ("email", "phone", "email_hash", "requester_email",
                                         "requester_name", "requester_phone") if k in ev}
        direct = ev.get("direct_identifiers")
        if direct is not None:
            pii = direct not in ("0", 0)
        elif "message_text" in ev:
            pii = ev["message_text"] != "[REDACTED]"
        else:
            pii = any(v not in NULLS for v in fields.values())
        return (PRESENT, pii, None)
    if name in {"connector_config_read_completed", "connector_heartbeat", "connector_config_loaded"}:
        on = truthy(ev.get("enabled"))
        return (ACTIVE if on else DISABLED, None, "DATA_FLOW") if on is not None else None
    if name == "restore_policy_read_completed":
        allowed = truthy(ev.get("restore_allowed"))
        return (ACTIVE if allowed else BLOCKED, None, "BACKUP_ARCHIVE") if allowed is not None else None
    if name == "restore_candidate_evaluated":
        eligible, blocked = truthy(ev.get("eligible")), truthy(ev.get("deletion_block"))
        return (BLOCKED if (blocked or eligible is False) else ACTIVE, None, "BACKUP_ARCHIVE")
    if name == "restore_authorization_completed":
        return (BLOCKED if ev.get("decision") == "deny" else ACTIVE, None, "BACKUP_ARCHIVE")
    if name == "retained_order_loaded":      # legal_service read of a retained order under legal hold
        return (PRESENT, None, "LEGAL_HOLD_RECORD")
    if name in {"export_metadata_read_completed", "export_download_check_completed"}:
        avail = truthy(ev.get("available"))
        return (PRESENT if avail is not False else ABSENT, None, "USER_EXPORT")
    return None


def _lookup_presence(rows, status) -> bool | None:
    """Return whether a lookup found rows, without treating errors as empty results."""
    status = str(status).strip() if status is not None else ""
    if status and status not in {"200", "404"}:
        return None
    if rows is not None:
        try:
            count = int(str(rows).strip())
        except (TypeError, ValueError):
            count = None
        if count is not None and count >= 0:
            return count > 0
    if status == "200":
        return True
    if status == "404":
        return False
    return None


def parse_log(path: Path, file_id: str, captured_at: str):
    events = [ev for ev in (parse_line(l) for l in path.read_text(encoding="utf-8").splitlines()) if ev]
    by_trace: dict[str, list] = {}
    for ev in events:
        if ev.get("trace_id"):
            by_trace.setdefault(ev["trace_id"], []).append(ev)

    observations = []
    for ev in events:
        if ev.get("service") in NOISE_SERVICES:
            continue
        rid = ev.get("resource_id", "")
        if not rid or not system_for(rid):
            continue
        implied = _event_state(ev)
        if implied is None:
            continue
        state, pii, rtype = implied
        # Gather identity from this line and its trace siblings (the *_started lookup keys).
        fields = {k: v for k, v in ev.items() if isinstance(v, str)}
        trace_fields = {}
        for sib in by_trace.get(ev.get("trace_id"), []):
            if sib is ev:
                continue
            for k, v in sib.items():
                if isinstance(v, str) and k not in ("resource_id",):
                    trace_fields.setdefault(k, v)
        merged = {**trace_fields, **fields}
        if ev.get("event") == "record_lookup" and "subject_reference" in ev:
            merged["subject_reference"] = ev["subject_reference"]
        ids = extract_identifiers(merged)
        # Lookup keys that are the resource id itself are not identity.
        ids["users"] = {u for u in ids["users"] if u != rid}
        observations.append(Observation(
            evidence_id=file_id, observed_at=ev["ts"], captured_at=captured_at,
            system_id=system_for(rid), resource_id=rid,
            record_type=rtype or ev.get("record_type") or record_type_for(rid),
            state=state, pii=pii, emails=ids["emails"], hashes=ids["hashes"], users=ids["users"],
            phones=ids["phones"], source=f"log:{path.name}:{ev.get('event')}",
            attrs={k: v for k, v in merged.items() if k not in ("ts",)},
        ))
    return observations, []


__all__ = ["parse_log", "parse_line", "classify_value"]

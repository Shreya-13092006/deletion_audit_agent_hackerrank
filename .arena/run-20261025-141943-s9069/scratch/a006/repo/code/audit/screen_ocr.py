"""Turn local OCR output (words with boxes) of a console screenshot into structured records.

Deterministic and closed-world: an identifier read from a screen is accepted only when it
matches an identifier that already exists elsewhere in the participant data (resource ids in
evidence/activity, emails and user_ids in the identity tables, business references from
catalog links). OCR character confusions (I/l/1, O/0, S/5, g/9, B/8) are repaired only when
the repair yields exactly one such known identifier - nothing is invented.
"""
from __future__ import annotations

import re

PREFIXES = ("account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|"
            "legal_hold|marketing|object")
RESOURCE_RE = re.compile(rf"\b({PREFIXES})\s*_\s*([0-9IlOoSsgBZ|]{{1,6}})(?![\w])")
USER_RE = re.compile(r"\buser\s*_\s*([0-9IlOoSs|]{1,5})(?![\w])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
DIGIT_FIX = str.maketrans({"I": "1", "l": "1", "|": "1", "O": "0", "o": "0", "S": "5", "s": "5",
                           "g": "9", "B": "8", "Z": "2"})
LETTER_SWAPS = [("I", "l"), ("l", "I"), ("0", "o"), ("1", "l"), ("rn", "m")]
ROW_TOLERANCE = 12          # px at 1x scale: lines whose centres are this close form one table row

ACTIVE_WORDS = re.compile(r"\b(continuous|healthy|active|live|enabled|running)\b", re.I)
INACTIVE_WORDS = re.compile(r"\b(disabled|paused|stopped|inactive)\b", re.I)
BLOCKED_WORDS = re.compile(r"\b(restore blocked|blocked|legal hold|deletion block)\b", re.I)
TYPE_BY_PREFIX = {"account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "analytics": "ANALYTICS_PROFILE",
                  "support": "SUPPORT_MESSAGE", "export": "USER_EXPORT", "data_flow": "DATA_FLOW",
                  "backup": "BACKUP_ARCHIVE", "audit_record": "SECURITY_AUDIT_LOG",
                  "tombstone": "ACCOUNT_TOMBSTONE", "legal_hold": "LEGAL_HOLD_RECORD",
                  "marketing": "MARKETING_PROFILE", "object": "SUPPORT_ATTACHMENT"}


def lines_from(ocr: dict, scale: int) -> list[dict]:
    """Normalize OCR lines to 1x coordinates: [{text, x0, x1, yc, scale}]."""
    out = []
    for line in ocr.get("lines", []):
        words = line.get("words") or []
        if not words:
            continue
        x0 = min(w["x"] for w in words) / scale
        x1 = max(w["x"] + w["w"] for w in words) / scale
        yc = sum(w["y"] + w["h"] / 2 for w in words) / len(words) / scale
        out.append({"text": line["text"], "x0": x0, "x1": x1, "yc": yc, "scale": scale})
    return out


def _resolve_email(raw: str, known_emails: set) -> str | None:
    cand = raw.strip().strip(".").lower()
    if cand in known_emails:
        return cand
    variants = set()
    for a, b in LETTER_SWAPS:
        if a in raw:
            variants.add(raw.replace(a, b).strip().strip(".").lower())
    hits = variants & known_emails
    return hits.pop() if len(hits) == 1 else None


def _resolve_id(prefix: str, digits: str, known: set) -> str | None:
    exact = f"{prefix}_{digits}"
    if exact in known:
        return exact
    fixed = f"{prefix}_{digits.translate(DIGIT_FIX)}"
    return fixed if fixed in known and fixed[len(prefix) + 1:].isdigit() else None


def parse_screen(ocr_by_scale: dict, known_resources: set, known_emails: set, known_users: set,
                 reference_index: dict) -> tuple[list[dict], list[str], str]:
    """Return (records, rejected_tokens, screen_title)."""
    lines = []
    for key, ocr in sorted(ocr_by_scale.items(), reverse=True):     # "2g", "2", "1"
        for line in lines_from(ocr, int(key[0])):
            line["reading"] = key
            lines.append(line)
    rejected: set = set()
    page_text = " ".join(l["text"] for l in lines)

    def ids_in(text: str) -> tuple[set, set]:
        emails, users = set(), set()
        for raw in EMAIL_RE.findall(text):
            hit = _resolve_email(raw, known_emails)
            (emails.add(hit) if hit else rejected.add(raw))
        for digits in USER_RE.findall(text):
            uid = _resolve_id("user", digits, known_users)
            (users.add(uid) if uid else rejected.add(f"user_{digits}"))
        return emails, users

    # Identifiers unknown elsewhere are accepted only when at least two independent OCR
    # readings (1x, 2x, 2x grayscale) give the same digits after confusion repair.
    readings: dict[str, set] = {}
    for line in lines:
        for prefix, digits in RESOURCE_RE.findall(line["text"]):
            readings.setdefault(line["reading"], set()).add(f"{prefix}_{digits.translate(DIGIT_FIX)}")
    votes: dict[str, int] = {}
    for ids in readings.values():
        for rid in ids:
            votes[rid] = votes.get(rid, 0) + 1
    agreed = {r for r, n in votes.items() if n >= 2 and r.rsplit("_", 1)[1].isdigit()}

    anchors: dict[str, list] = {}
    for line in lines:
        for prefix, digits in RESOURCE_RE.findall(line["text"]):
            rid = _resolve_id(prefix, digits, known_resources | agreed)
            if rid:
                anchors.setdefault(rid, []).append(line)
            else:
                rejected.add(f"{prefix}_{digits}")
        lowered = line["text"].lower()
        for ref, rids in reference_index.items():
            if ref.lower() in lowered and not ref.startswith("user_"):
                for rid in rids:
                    anchors.setdefault(rid, []).append(line)
    # A retained-reference registry page names only the stable user reference.
    for ref, rids in reference_index.items():
        if ref.startswith("user_") and re.search(rf"\b{re.escape(ref)}\b", page_text) \
                and re.search(r"retained reference", page_text, re.I):
            for rid in rids:
                anchors.setdefault(rid, []).append({"text": ref, "yc": -1, "x0": 0, "x1": 0})

    page_emails, page_users = ids_in(page_text)
    single_focus = len(anchors) == 1
    records = []
    for rid, hits in sorted(anchors.items()):
        row_text = []
        for anchor in hits:
            row_text.extend(l["text"] for l in lines if abs(l["yc"] - anchor["yc"]) <= ROW_TOLERANCE)
            row_text.append(anchor["text"])
        emails, users = ids_in(" ".join(row_text))
        row_unknown = [t for t in EMAIL_RE.findall(" ".join(row_text))
                       if _resolve_email(t, known_emails) is None]
        if single_focus and not emails and not users:
            emails, users = page_emails, page_users
        elif not emails and not users and not row_unknown and len(page_users) == 1:
            users = set(page_users)              # the page's single subject (e.g. a subject filter)
        prefix = rid.rsplit("_", 1)[0]
        rtype = TYPE_BY_PREFIX.get(prefix)
        rec = {"resource_id": rid, "record_type": rtype, "related_resource_ids": []}
        if row_unknown or (single_focus and not emails and EMAIL_RE.search(page_text)):
            shown = sorted(set(row_unknown) or {t for t in EMAIL_RE.findall(page_text)
                                                 if _resolve_email(t, known_emails) is None})
            if shown:
                rec["note"] = "contact not in identity tables: " + ", ".join(t.lower() for t in shown)
        if len(emails) == 1:
            rec["email"] = next(iter(emails))
        if len(users) == 1:
            rec["customer_reference"] = next(iter(users))
        context = " ".join(row_text) + " " + (page_text if single_focus else "")
        if rtype == "DATA_FLOW":
            if INACTIVE_WORDS.search(context):
                rec.update(result="DISABLED", enabled=False)
            elif ACTIVE_WORDS.search(context):
                rec.update(result="ACTIVE", enabled=True)
        elif rtype == "BACKUP_ARCHIVE":
            blocked = bool(BLOCKED_WORDS.search(context))
            rec.update(result="BLOCKED" if blocked else "ACTIVE", restore_allowed=not blocked)
        elif rtype == "ACCOUNT_TOMBSTONE":
            rec["result"] = "IDENTIFIABLE" if rec.get("email") else "REDACTED"
        elif rtype == "SECURITY_AUDIT_LOG":
            rec["result"] = "FOUND"
        else:
            rec["result"] = "IDENTIFIABLE" if rec.get("email") else "FOUND"
        records.append(rec)
    title = next((l["text"] for l in lines if len(l["text"]) > 6), "")
    return records, sorted(rejected), title

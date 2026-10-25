"""Independent, read-only verifier for a predictions CSV (standard library only).

It recomputes every check from the raw files in dataset/ and never imports code/audit/*, so a bug
shared by the pipeline cannot hide here. The only derived inputs it reads are the shipped
extraction caches (code/cache/image_facts.json for screenshots, pdf_text.json for PDFs), as data.

Usage (from the repository root):
    python code/evaluation/verify_output.py                     # root output.csv vs deletion_requests.csv
    python code/evaluation/verify_output.py --split sample --pred sample_predictions.csv

FAIL (exit code 1) - hard contract and evidence rules:
    rows / header / sort / statuses / JSON / step keys and numbering / phase-operation-state /
    order / evidence required or forbidden / cited id exists / cited before audit_at /
    cited file covers the resource (direct, absence by omission from a snapshot of that system,
    or a reference link) / finding ownership tied to the requester / COMPLETE = cited verifications
WARN - heuristic reads of the raw text (state wording, policy by record type); review, not proof.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
D = REPO / "dataset"
CACHE = REPO / "code" / "cache"

OPS = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
       "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
       "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
       "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]
STATE = dict(zip(OPS, ["PRESENT", "PRESENT", "ACTIVE", "ACTIVE", "DISABLED", "BLOCKED", "ABSENT", "REDACTED",
                       "ANONYMIZED", "ABSENT", "PRESENT", "REDACTED", "ANONYMIZED", "DISABLED", "BLOCKED"]))
PHASE = {o: "FINDING" if o.startswith("REPORT") else "VERIFICATION" if o.startswith("VERIFY") else "REMEDIATION"
         for o in OPS}
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
PREFIX_TYPE = {"account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "analytics": "ANALYTICS_PROFILE",
               "support": "SUPPORT_MESSAGE", "export": "USER_EXPORT", "audit_record": "SECURITY_AUDIT_LOG",
               "legal_hold": "LEGAL_HOLD_RECORD", "backup": "BACKUP_ARCHIVE", "data_flow": "DATA_FLOW",
               "tombstone": "ACCOUNT_TOMBSTONE", "marketing": "MARKETING_PROFILE", "object": "SUPPORT_ATTACHMENT",
               "telemetry": "PRODUCT_TELEMETRY", "cache": "CACHE_ENTRY", "email_log": "EMAIL_DELIVERY_LOG"}
FINAL = {"DELETE": "VERIFY_RECORD_ABSENT", "REDACT": "VERIFY_RECORD_REDACTED",
         "ANONYMIZE": "VERIFY_RECORD_ANONYMIZED", "RETAIN": "VERIFY_RECORD_PRESENT"}
RID = re.compile(r"\b[a-z][a-z_]*?_\d+\b")
# Explicit category labels in the raw evidence (table / collection / record_type values).
LABELS = {"SUPPORT_ATTACHMENT": ("support_attachment", "ticket_attachments"),
          "SUPPORT_MESSAGE": ("support_message", "support_conversations")}
# Weak hints: never set a category, only reveal a conflict with an explicit label (messages can
# also carry attachment scans).
HINTS = {"SUPPORT_ATTACHMENT": ("attachment_pii_scan",), "SUPPORT_MESSAGE": ("message_pii_scan",)}
TRUE = r"(?:true|active|allowed|enabled|'1'|=1\b|\"1\")"
FALSE = r"(?:false|disabled|blocked|deny|'0'|=0\b|\"0\")"


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class Data:
    def __init__(self):
        self.man = {r["file_id"]: r for r in read_csv(D / "evidence_files.csv")}
        self.acts = read_csv(D / "system_activity.csv")
        self.act_time = {a["activity_id"]: a["event_time"] for a in self.acts}
        self.act_by: dict = {}
        for a in self.acts:
            self.act_by.setdefault(a["resource_id"], []).append(a)
        self.audit = read_csv(D / "user_audit_log.csv")
        self.audit_time = {a["audit_id"]: a["event_time"] for a in self.audit}
        self.users = {r["user_id"]: r for r in read_csv(D / "user_identities.csv")}
        self.rules = {r["data_category"]: r["required_action"] for r in read_csv(D / "deletion_rules.csv")}
        img = json.loads((CACHE / "image_facts.json").read_text(encoding="utf-8"))
        pdf = json.loads((CACHE / "pdf_text.json").read_text(encoding="utf-8"))
        self.units = {f: [u.lower() for u in self._units(f, img, pdf)] for f in self.man}
        self.raw = {f: self._raw(f, img, pdf).lower() for f in self.man}     # whole file, incl. scope keys
        self.index: dict = {}                                                # resource id -> [(file, unit)]
        for f, units in self.units.items():
            for u in units:
                for rid in set(RID.findall(u)):
                    self.index.setdefault(rid, []).append((f, u))

    def _raw(self, f, img, pdf) -> str:
        p = D / self.man[f]["file_path"]
        if p.suffix == ".png":
            return json.dumps(img.get(f, {}))
        if p.suffix == ".pdf":
            return json.dumps(pdf.get(p.name, {}))
        return p.read_text(encoding="utf-8", errors="replace")

    def rows(self, rid: str, f: str | None = None) -> list[str]:
        return [u for g, u in self.index.get(rid, []) if f is None or g == f]

    def _units(self, f, img, pdf) -> list[str]:
        """Records of one file: JSON objects with a resource_id, SQL rows, log lines and whole traces."""
        p = D / self.man[f]["file_path"]
        if p.suffix == ".png":
            return [json.dumps(r) for r in img.get(f, {}).get("records", [])]
        if p.suffix == ".pdf":
            return [json.dumps(pdf.get(p.name, {}))]
        t = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix == ".json":
            out: list = []

            def walk(x):
                if isinstance(x, dict):
                    if "resource_id" in x:
                        out.append(json.dumps(x))
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)
            walk(json.loads(t))
            return out
        lines = t.splitlines()
        traces: dict = {}
        for line in lines:
            m = re.search(r"\b(?:tr|rb)-[\w-]+", line) or re.search(r"trace_id=([\w-]+)", line)
            if m:
                traces.setdefault(m.group(0), []).append(line)
        return lines + [" ".join(v) for v in traces.values()]

    def subject(self, email: str):
        e = email.strip().lower()
        uid = next((u for u, r in self.users.items() if r["email"].lower() == e), None) or \
            next((a["user_id"] for a in self.audit if a["field_name"] == "email"
                  and e in (a["old_value"].lower(), a["new_value"].lower())), None)
        if uid is None:
            return None, {e, hashlib.sha256(e.encode()).hexdigest()}
        ids = {uid, self.users[uid]["email"].lower()}
        ids |= {v.lower() for a in self.audit if a["user_id"] == uid and a["field_name"] in ("email", "email_hash")
                for v in (a["old_value"], a["new_value"]) if v}
        ids |= {hashlib.sha256(x.encode()).hexdigest() for x in list(ids) if "@" in x}
        return uid, ids


def has_id(unit: str, ids: set) -> bool:
    return any(re.search(r"(?<![\w.@-])" + re.escape(i) + r"(?![\w@-])", unit) for i in ids)


def mentions(unit: str, rid: str) -> bool:
    return re.search(r"\b" + re.escape(rid) + r"\b", unit) is not None


def record_type(d: Data, rid: str) -> tuple[str | None, bool]:
    """(record type, explicit) - explicit when the raw evidence labels the category itself.

    Policy is judged only on explicit labels: a support message vs a subject-only attachment, or a
    contact / opt-in analytics record, cannot be told apart reliably from the id prefix alone.
    """
    prefix = next((p for p in sorted(PREFIX_TYPE, key=len, reverse=True) if rid.startswith(p + "_")), None)
    joined = " ".join(d.rows(rid))
    found = {t for t, words in LABELS.items() if any(w in joined for w in words)}
    found |= {t for t in ("MARKETING_PROFILE", "SECONDARY_IDENTIFIER", "EMAIL_DELIVERY_LOG", "PRODUCT_TELEMETRY",
                          "CACHE_ENTRY") if t.lower() in joined}
    hinted = {t for t, words in HINTS.items() if any(w in joined for w in words)}
    if len(found) == 1 and hinted - found:
        found |= hinted
    if len(found) == 1:
        return found.pop(), True
    if len(found) > 1:
        return "CONFLICT:" + "/".join(sorted(found)), False
    return PREFIX_TYPE.get(prefix), prefix not in ("support", "analytics")


def covers_by_omission(d: Data, ev: str, rid: str) -> bool:
    """A snapshot that holds records of the resource's system but not the resource itself."""
    prefix = rid.rsplit("_", 1)[0] + "_"
    t = d.raw[ev]
    system_rows = re.search(re.escape(prefix) + r"\d+", t) is not None
    declared = "snapshot_scope" in t or '"data_store"' in t
    return (system_rows or declared) and not mentions(t, rid)


def reference_link(d: Data, ev: str, rid: str) -> bool:
    """LINK_RESOURCE_IDENTITY activity naming a business reference that appears in the cited file."""
    for a in d.act_by.get(rid, []):
        if a["event_type"] == "LINK_RESOURCE_IDENTITY":
            for ref in re.findall(r"\(([A-Z0-9-]{6,})\)", a["details"]):
                if ref.lower() in d.raw[ev]:
                    return True
    return False


def state_supported(d: Data, step: dict) -> bool:
    rows = " ".join(d.rows(step["resource_id"].lower(), step["evidence_id"]))
    op = step["operation"]
    if not rows:
        return op == "VERIFY_RECORD_ABSENT"
    if op == "VERIFY_RECORD_ABSENT":
        return re.search(r"404|not_found|rows\W{0,3}0\b|absent|marker_found=false|deleted", rows) is not None
    if op == "REPORT_EXPOSED_PII":
        return re.search(r"@|\+\d|user_\d+|identifiable|direct_identifier", rows) is not None
    if op in ("VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED"):
        return re.search(r"redacted|anonymi[sz]ed|null|none", rows) is not None
    if op in ("REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"):
        return re.search(TRUE, rows) is not None
    if op in ("VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"):
        return re.search(FALSE, rows) is not None
    return True


def finding_owned(d: Data, rid: str, uid, ids: set, audit_at: str) -> bool:
    if any(d.man[f]["captured_at"] <= audit_at and has_id(u, ids) for f, u in d.index.get(rid, [])):
        return True
    return any(a["event_type"] == "LINK_RESOURCE_IDENTITY" and a["event_time"] <= audit_at
               and ((uid and uid in a["details"]) or any(i in a["details"].lower() for i in ids))
               for a in d.act_by.get(rid, []))


def verify(pred_path: Path, req_path: Path) -> tuple[list, list, dict]:
    d = Data()
    req = {r["case_id"]: r for r in read_csv(req_path)}
    fails, warns = [], []
    stats = {"rows": 0, "citations": 0, "findings": 0, "complete": 0}
    raw = pred_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        fails.append(("file", "UTF-8 BOM present"))
    with open(pred_path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    if header != ["case_id", "deletion_status", "steps_json"]:
        fails.append(("file", f"header {header}"))
    ids = [r[0] for r in rows]
    stats["rows"] = len(rows)
    if len(ids) != len(set(ids)) or set(ids) != set(req):
        fails.append(("file", f"case ids: {len(ids)} rows, {len(set(ids))} unique, "
                              f"missing {sorted(set(req) - set(ids))[:5]}, extra {sorted(set(ids) - set(req))[:5]}"))
    if ids != sorted(ids, key=lambda c: int(c.rsplit("_", 1)[1])):
        fails.append(("file", "rows not sorted by case_id"))
    for row in rows:
        if len(row) != 3:
            fails.append((row[0], "row does not have 3 fields"))
            continue
        cid, status, sj = row
        case = req.get(cid)
        if case is None:
            continue
        if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
            fails.append((cid, f"status {status}"))
        try:
            steps = json.loads(sj)
        except ValueError as exc:
            fails.append((cid, f"steps_json: {exc}"))
            continue
        if not isinstance(steps, list) or (status == "NOT_APPLICABLE") != (steps == []):
            fails.append((cid, "NOT_APPLICABLE must be [] and only NOT_APPLICABLE may be []"))
            continue
        uid, sub_ids = d.subject(case["email"])
        prev = None
        by_rid: dict = {}
        for i, s in enumerate(steps, 1):
            if not isinstance(s, dict) or set(s) != KEYS:
                fails.append((cid, f"step {i} keys"))
                continue
            op = s["operation"]
            if s["step_no"] != i:
                fails.append((cid, f"step {i} step_no={s['step_no']}"))
            if op not in STATE or STATE[op] != s["state"] or PHASE[op] != s["phase"]:
                fails.append((cid, f"step {i} operation/state/phase {op}/{s['state']}/{s['phase']}"))
                continue
            key = (PHASES.index(s["phase"]), OPS.index(op), s["system_id"], s["resource_id"])
            if prev and key < prev:
                fails.append((cid, f"step {i} out of order"))
            prev = key
            by_rid.setdefault(s["resource_id"], []).append(op)
            ev, needs = s["evidence_id"], s["phase"] == "FINDING" or status == "COMPLETE"
            if needs and not ev:
                fails.append((cid, f"step {i} {op} needs evidence"))
            if not needs and ev:
                fails.append((cid, f"step {i} future step must have empty evidence"))
            if not ev:
                continue
            stats["citations"] += 1
            when = (d.man.get(ev) or {}).get("captured_at") or d.act_time.get(ev) or d.audit_time.get(ev)
            if when is None:
                fails.append((cid, f"step {i} unknown evidence {ev}"))
                continue
            if when > case["audit_at"]:
                fails.append((cid, f"step {i} cites {ev} captured after audit_at"))
                continue
            if ev in d.man:
                rid = s["resource_id"].lower()
                direct = bool(d.rows(rid, ev))
                omission = not direct and op == "VERIFY_RECORD_ABSENT" and covers_by_omission(d, ev, rid)
                reference = not direct and not omission and reference_link(d, ev, s["resource_id"])
                if not (direct or omission or reference):
                    fails.append((cid, f"step {i} {ev} does not cover {s['resource_id']}"))
                elif direct and not state_supported(d, s):
                    warns.append((cid, f"step {i} {op} {s['resource_id']}: state wording not found in {ev}"))
            if s["phase"] == "FINDING":
                stats["findings"] += 1
                if not finding_owned(d, s["resource_id"].lower(), uid, sub_ids, case["audit_at"]):
                    fails.append((cid, f"step {i} finding on {s['resource_id']} not tied to the requester"))
        if status == "COMPLETE":
            stats["complete"] += 1
            if any(s.get("phase") != "VERIFICATION" or not s.get("evidence_id") for s in steps):
                fails.append((cid, "COMPLETE must contain only cited verifications"))
        for rid, ops in by_rid.items():
            rtype, explicit = record_type(d, rid.lower())
            if rtype and rtype.startswith("CONFLICT:"):
                warns.append((cid, f"{rid}: conflicting category evidence ({rtype[9:]}); output uses {ops}"))
                continue
            if rtype in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD") and ("DELETE_RECORD" in ops or
                                                                          "VERIFY_RECORD_ABSENT" in ops):
                fails.append((cid, f"retained record {rid} deleted"))
            want = {"DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED", "BACKUP_ARCHIVE": "VERIFY_RESTORE_BLOCKED"}.get(
                rtype, FINAL.get(d.rules.get(rtype or "", "")))
            verify_ops = [o for o in ops if o.startswith("VERIFY_")]
            if explicit and want and verify_ops and want not in verify_ops:
                warns.append((cid, f"{rid}: {verify_ops} but policy for {rtype} is {want}"))
    return fails, warns, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["eval", "sample"], default="eval")
    ap.add_argument("--pred", type=Path)
    args = ap.parse_args(argv)
    req = D / ("deletion_requests.csv" if args.split == "eval" else "sample_deletion_requests.csv")
    pred = args.pred or REPO / ("output.csv" if args.split == "eval" else "sample_predictions.csv")
    fails, warns, stats = verify(pred, req)
    print(f"{pred.name}: sha256 {hashlib.sha256(pred.read_bytes()).hexdigest()}")
    print(f"rows {stats['rows']}  |  citations {stats['citations']}  |  findings {stats['findings']}  |  "
          f"COMPLETE {stats['complete']}  |  FAIL {len(fails)}  |  WARN {len(warns)}")
    for f in fails[:50]:
        print("  FAIL", *f)
    for w in warns[:50]:
        print("  WARN", *w)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

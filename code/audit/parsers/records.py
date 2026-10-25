"""JSON and plain-text record files -> Observations + scope covers.

Families are recognised by structure (file names do not describe content):
  * snapshot bundles      {"snapshots": [{data_store, collection, captured_at, records}]}
  * service exports       {"service_exports": {system: {section: [rows with observed_at]}}}
  * record_lookup ledgers {"records": [{system, resource_id, record_type, result, subject_reference}]}
  * focused collections   {"collection": ..., "records": [...]}
  * handover text         "- ts | system | resource | RECORD_TYPE | RESULT | subject"
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..schema import ABSENT, PRESENT, ScopeCover
from .common import record_observation

LEDGER_COLLECTION = "operational_record_history"


def _ledger_row(row: dict) -> dict:
    """Normalize a record_lookup row: subject/lookup value become identity fields."""
    out = dict(row)
    subject = out.pop("subject_reference", None) or out.pop("lookup_value", None)
    if subject is not None:
        out["subject_reference"] = subject
    return out


def parse_json(path: Path, file_id: str, captured_at: str):
    data = json.loads(path.read_text(encoding="utf-8"))
    observations, covers = [], []

    def add(record, observed_at, collection, source, system_hint=None):
        obs = record_observation(record, evidence_id=file_id, observed_at=observed_at,
                                 captured_at=captured_at, collection=collection, source=source,
                                 system_hint=system_hint)
        if obs is not None:
            observations.append(obs)
        return obs

    if "snapshots" in data:
        scope: dict[tuple, set] = {}                    # (data_store, captured_at) -> present ids
        for snap in data["snapshots"]:
            at = snap.get("captured_at") or captured_at
            coll = snap.get("collection")
            if coll == LEDGER_COLLECTION:
                for row in snap.get("records", []):
                    add(_ledger_row(row), row.get("recorded_at") or at, None, f"bundle-ledger:{path.name}")
                continue
            present = scope.setdefault((snap["data_store"], at), set())
            for row in snap.get("records", []):
                obs = add(row, at, coll, f"bundle:{path.name}:{coll}", snap.get("data_store"))
                if obs:
                    present.add(obs.resource_id)
        for (store_name, at), present in scope.items():
            covers.append(ScopeCover(file_id, at, store_name, frozenset(present)))

    elif "service_exports" in data:
        for system, sections in data["service_exports"].items():
            for section, rows in sections.items():
                for row in rows:
                    at = row.get("observed_at") or captured_at
                    if section == "index_queries":
                        hits = (row.get("hits") or {}).get("documents") or []
                        for doc in hits:
                            add(doc, at, "customer_search_documents", f"sre:{path.name}:{section}", system)
                        if not hits:
                            obs = add({"resource_id": row["resource_id"], "query": row.get("query")},
                                      at, "customer_search_documents", f"sre:{path.name}:{section}", system)
                            if obs:
                                obs.state = ABSENT
                                if row.get("query"):
                                    obs.attrs["lookup_key"] = row["query"]
                        continue
                    add(row, at, None, f"sre:{path.name}:{section}", system)

    elif isinstance(data.get("records"), list):
        coll = data.get("collection")
        at_default = data.get("captured_at") or data.get("exported_at") or captured_at
        for row in data["records"]:
            if "result" in row and "record_type" in row:
                add(_ledger_row(row), row.get("recorded_at") or at_default, None, f"ledger:{path.name}")
            else:
                add(row, at_default, coll, f"collection:{path.name}:{coll}")
    return observations, covers


HANDOVER_RE = re.compile(r"^-\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(.*)$")


def parse_text(path: Path, file_id: str, captured_at: str):
    observations = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HANDOVER_RE.match(line.strip())
        if not m:
            continue
        ts, system, rid, rtype, result, subject = m.groups()
        row = {"resource_id": rid, "system": system, "record_type": rtype, "result": result,
               "subject_reference": subject.strip() or None}
        obs = record_observation(row, evidence_id=file_id, observed_at=ts, captured_at=captured_at,
                                 collection=None, source=f"text:{path.name}", system_hint=system)
        if obs:
            observations.append(obs)
    return observations, []


__all__ = ["parse_json", "parse_text", "PRESENT"]

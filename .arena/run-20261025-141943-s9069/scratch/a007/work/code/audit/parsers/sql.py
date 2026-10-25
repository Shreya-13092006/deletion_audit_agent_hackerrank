"""SQLite snapshot exports -> Observations + scope covers + resource links.

Each .sql file is executed into a private in-memory database (the dataset is never written).
Four schema families exist; adapters are chosen by table shape, not by file name.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..aliases import system_for
from ..schema import ScopeCover
from .common import record_observation


def _rows(db, table):
    cur = db.execute(f'SELECT * FROM "{table}"')
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def parse_sql(path: Path, file_id: str, captured_at: str):
    db = sqlite3.connect(":memory:")
    db.executescript(path.read_text(encoding="utf-8"))
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    observations, covers, links = [], [], []
    present_by_system: dict[str, set] = {}
    scope: dict[str, str] = {}

    if "snapshot_scope" in tables:
        for row in _rows(db, "snapshot_scope"):
            scope[row["origin_system"]] = row["captured_at"]

    for table in tables:
        if table == "snapshot_scope":
            continue
        for row in _rows(db, table):
            if "record_json" in row:                      # replica-pair family
                record = json.loads(row["record_json"])
                collection, replica = row.get("collection_name"), table
            else:                                         # typed tables
                record, collection, replica = dict(row), table, table
                if "user_id" in record and "customer_reference" not in record:
                    record["customer_reference"] = record.pop("user_id")
                for key in ("updated_at", "indexed_at"):
                    record.pop(key, None)
            obs = record_observation(record, evidence_id=file_id, observed_at=captured_at,
                                     captured_at=captured_at, collection=_collection(collection),
                                     source=f"sql:{path.name}:{table}", replica=replica)
            if obs is None:
                continue
            observations.append(obs)
            present_by_system.setdefault(obs.system_id, set()).add(obs.resource_id)
            src = record.get("source_resource_id")
            if src:                                       # search document -> its account
                links.append((obs.resource_id, str(src), file_id))

    # Scope: inventory files declare it; other families cover every system they contain.
    if scope:
        for system, at in scope.items():
            covers.append(ScopeCover(file_id, at, system,
                                     frozenset(present_by_system.get(system, set()))))
    else:
        for system, rids in present_by_system.items():
            covers.append(ScopeCover(file_id, captured_at, system, frozenset(rids)))
    db.close()
    return observations, covers, links


def _collection(name: str | None) -> str | None:
    """Typed failover/primary tables reuse the canonical collection names."""
    if not name:
        return name
    for suffix in ("_failover_replica", "_primary"):
        if name.startswith("customer_profiles") and name.endswith(suffix):
            return "customer_profiles"
    return name


__all__ = ["parse_sql", "system_for"]

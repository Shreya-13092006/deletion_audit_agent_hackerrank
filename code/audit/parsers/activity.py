"""system_activity.csv: operation claims, explicit identity links and recreation signals.

`reported_result` values are claims and never prove a resource's state. Only read-only state
checks (CHECK_DATA_FLOW / CHECK_RESTORE_ACCESS) and catalog links are turned into facts.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..aliases import RESOURCE_RE, classify_value, record_type_for, system_for
from ..schema import ACTIVE, Observation

LINK_RE = re.compile(r"linked (\S+) \(([^)]+)\) to (\S+) and (user_\d+)")
ATTACH_RE = re.compile(r"confirmed (\S+) \(([^)]+)\) belongs only to (\S+) and (user_\d+)")
REPOPULATED_RE = re.compile(r"repopulated downstream resource (\S+?)\.?$")


@dataclass
class ActivityIndex:
    rows: list = field(default_factory=list)
    observations: list = field(default_factory=list)     # identity links + state checks
    reference_index: dict = field(default_factory=dict)  # business reference -> resource ids
    non_deletion_resources: dict = field(default_factory=dict)  # resource -> activity row
    recreation_links: list = field(default_factory=list)  # (source_resource, downstream, activity)
    account_deletes: list = field(default_factory=list)   # account DELETE_RECORD rows
    by_resource: dict = field(default_factory=dict)


def load_activity(dataset_dir: Path) -> ActivityIndex:
    idx = ActivityIndex()
    with open(dataset_dir / "system_activity.csv", encoding="utf-8", newline="") as fh:
        idx.rows = list(csv.DictReader(fh))
    for row in idx.rows:
        rid, et, details = row["resource_id"], row["event_type"], row["details"]
        idx.by_resource.setdefault(rid, []).append(row)
        if et == "LINK_RESOURCE_IDENTITY":
            m = LINK_RE.search(details) or ATTACH_RE.search(details)
            if m:
                res, ref, email, user = m.groups()
                if ref != res:
                    idx.reference_index.setdefault(ref, set()).add(res)
                obs = Observation(
                    evidence_id=row["activity_id"], observed_at=row["event_time"],
                    captured_at=row["event_time"], system_id=system_for(res) or row["target_system"],
                    resource_id=res, record_type=record_type_for(res), state="LINK",
                    source="activity:link", attrs={"reference": ref, "details": details})
                hit = classify_value(email.rstrip("."))
                if hit and hit[0] == "email":
                    obs.emails.add(hit[1])
                obs.users.add(user)
                if ATTACH_RE.search(details):
                    obs.attrs["sole_owner"] = True
                idx.observations.append(obs)
        elif et == "CLASSIFY_REQUEST" and "non-deletion" in details:
            idx.non_deletion_resources[rid] = row
        elif et in ("SYNC_RECORD", "RESTORE_BACKUP"):
            m = REPOPULATED_RE.search(details)
            if m:
                idx.recreation_links.append((rid, m.group(1), row))
        elif et == "CHECK_DATA_FLOW" and "remains enabled" in details:
            idx.observations.append(_check(row, rid, "DATA_FLOW"))
        elif et == "CHECK_RESTORE_ACCESS" and "can still be restored" in details:
            idx.observations.append(_check(row, rid, "BACKUP_ARCHIVE"))
        if et == "DELETE_RECORD" and row["target_system"] == "account_service" \
                and rid.startswith("account_"):
            idx.account_deletes.append(row)
    return idx


def _check(row, rid, rtype) -> Observation:
    return Observation(evidence_id=row["activity_id"], observed_at=row["event_time"],
                       captured_at=row["event_time"], system_id=system_for(rid), resource_id=rid,
                       record_type=rtype, state=ACTIVE, source="activity:state_check",
                       attrs={"details": row["details"]})


__all__ = ["load_activity", "ActivityIndex", "RESOURCE_RE"]

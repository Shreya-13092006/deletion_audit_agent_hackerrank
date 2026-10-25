"""Evidence loading: every manifest file -> Observations, scope covers and resource links."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .activity import ActivityIndex, load_activity
from .documents import parse_image_cache, parse_pdf
from .logs import parse_log
from .records import parse_json, parse_text
from .sql import parse_sql


@dataclass
class EvidenceStore:
    manifest: dict
    observations: list = field(default_factory=list)
    covers: list = field(default_factory=list)
    links: list = field(default_factory=list)          # (resource_a, resource_b, evidence_id)
    activity: ActivityIndex | None = None
    errors: list = field(default_factory=list)


def load_manifest(dataset_dir: Path) -> dict:
    with open(dataset_dir / "evidence_files.csv", encoding="utf-8", newline="") as fh:
        return {r["file_id"]: r for r in csv.DictReader(fh)}


def load_evidence(dataset_dir: Path, image_cache: Path) -> EvidenceStore:
    manifest = load_manifest(dataset_dir)
    store = EvidenceStore(manifest=manifest)
    store.activity = load_activity(dataset_dir)
    store.observations.extend(store.activity.observations)
    for file_id, meta in sorted(manifest.items()):
        path = dataset_dir / meta["file_path"]
        at = meta["captured_at"]
        suffix = path.suffix.lower()
        try:
            if suffix == ".sql":
                obs, covers, links = parse_sql(path, file_id, at)
                store.links.extend(links)
            elif suffix == ".json":
                obs, covers = parse_json(path, file_id, at)
            elif suffix == ".log":
                obs, covers = parse_log(path, file_id, at)
            elif suffix == ".txt":
                obs, covers = parse_text(path, file_id, at)
            elif suffix == ".pdf":
                obs, covers = parse_pdf(path, file_id, at, store.activity.reference_index)
            else:                                   # images: read from the extraction cache
                continue
        except Exception as exc:                    # fail safe: record and keep going
            store.errors.append((file_id, repr(exc)))
            continue
        store.observations.extend(obs)
        store.covers.extend(covers)
    obs, links = parse_image_cache(image_cache, manifest)
    store.observations.extend(obs)
    store.links.extend(links)
    # A snapshot inside a bundle may predate the bundle file; the file's own capture time
    # still decides when the evidence became available.
    for cov in store.covers:
        cov.captured_at = max(cov.captured_at, manifest[cov.evidence_id]["captured_at"])
    return store

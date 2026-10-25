"""Evidence-card store: every normalized Observation persisted as one indexed JSON file.

`code/cache/evidence_cards.json` holds all evidence cards (SQL, JSON, logs, TXT, PDF,
screenshot facts and activity-derived facts) plus snapshot scopes, resource links and lookup
indexes, so any resource or identifier can be found without re-parsing the 94 evidence files.

The file is fingerprinted over everything that determines its content: the evidence bytes, the
manifest, system_activity.csv, the screenshot-facts cache, the parser source code and whether
`pdftotext` is available. A matching fingerprint loads the cards; anything else (missing,
corrupt, different fingerprint or schema) re-parses and rewrites the file. No wall-clock values
are stored, so the file is byte-identical across runs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import CARD_SCHEMA_VERSION, CODE_DIR
from ..parsers import EvidenceStore, load_evidence, load_manifest
from ..parsers.activity import load_activity
from ..schema import Observation, ScopeCover

OBS_FIELDS = ["evidence_id", "observed_at", "captured_at", "system_id", "resource_id", "record_type",
              "state", "pii", "emails", "hashes", "users", "phones", "source", "replica", "attrs"]
SET_FIELDS = ("emails", "hashes", "users", "phones")
SOURCE_FILES = ["audit/aliases.py", "audit/schema.py", "audit/screen_ocr.py", "audit/vision_schema.py",
                "audit/agent/cards.py"]


def fingerprint(dataset_dir: Path, image_cache: Path) -> str:
    h = hashlib.sha256()

    def feed(label: str, data: bytes) -> None:
        h.update(label.encode() + b"\0" + hashlib.sha256(data).digest())

    manifest = load_manifest(dataset_dir)
    feed("evidence_files.csv", (dataset_dir / "evidence_files.csv").read_bytes())
    feed("system_activity.csv", (dataset_dir / "system_activity.csv").read_bytes())
    for file_id, meta in sorted(manifest.items()):
        path = dataset_dir / meta["file_path"]
        feed(file_id, path.read_bytes() if path.exists() else b"<missing>")
    feed("image_facts", image_cache.read_bytes() if image_cache.exists() else b"<missing>")
    for rel in SOURCE_FILES + sorted(str(p.relative_to(CODE_DIR)).replace("\\", "/")
                                     for p in (CODE_DIR / "audit" / "parsers").glob("*.py")):
        p = CODE_DIR / rel
        feed(rel, p.read_bytes() if p.exists() else b"")
    pdf_cache = CODE_DIR / "cache" / "pdf_text.json"
    feed("pdf_text", pdf_cache.read_bytes() if pdf_cache.exists() else b"<missing>")
    feed("schema", str(CARD_SCHEMA_VERSION).encode())
    return h.hexdigest()


def card_of(obs: Observation) -> dict:
    card = {f: getattr(obs, f) for f in OBS_FIELDS}
    for f in SET_FIELDS:
        card[f] = sorted(card[f])
    return card


def observation_of(card: dict) -> Observation:
    kw = {f: card[f] for f in OBS_FIELDS}
    for f in SET_FIELDS:
        kw[f] = set(kw[f])
    return Observation(**kw)


def build_payload(store: EvidenceStore, fp: str) -> dict:
    cards = [card_of(o) for o in store.observations]
    index: dict = {"resource": {}, "email": {}, "hash": {}, "user": {}, "system": {}, "evidence": {}}
    for i, c in enumerate(cards):
        index["resource"].setdefault(c["resource_id"], []).append(i)
        index["system"].setdefault(c["system_id"], []).append(i)
        index["evidence"].setdefault(c["evidence_id"], []).append(i)
        for f, k in (("emails", "email"), ("hashes", "hash"), ("users", "user")):
            for v in c[f]:
                index[k].setdefault(v, []).append(i)
    return {
        "meta": {"schema_version": CARD_SCHEMA_VERSION, "fingerprint": fp, "cards": len(cards),
                 "covers": len(store.covers), "links": len(store.links), "parse_errors": len(store.errors)},
        "cards": cards,
        "covers": [{"evidence_id": c.evidence_id, "captured_at": c.captured_at, "system_id": c.system_id,
                    "resource_ids": sorted(c.resource_ids), "record_type": c.record_type} for c in store.covers],
        "links": [list(link) for link in store.links],
        "errors": [list(e) for e in store.errors],
        "index": index,
    }


class EvidenceCardStore:
    """Loaded card file + rehydrated EvidenceStore + fast lookups for the agent tools."""

    def __init__(self, payload: dict, store: EvidenceStore, source: str):
        self.payload = payload
        self.store = store
        self.source = source            # "cache" (loaded) or "rebuilt"
        self.index = payload["index"]

    @property
    def meta(self) -> dict:
        return self.payload["meta"]

    def cards_for_resource(self, resource_id: str) -> list[dict]:
        return [self.payload["cards"][i] for i in self.index["resource"].get(resource_id, [])]

    def cards_for_identifier(self, value: str) -> list[dict]:
        hits: set = set()
        for k in ("email", "hash", "user"):
            hits.update(self.index[k].get(value, []))
        return [self.payload["cards"][i] for i in sorted(hits)]

    def cards_for_evidence(self, evidence_id: str) -> list[dict]:
        return [self.payload["cards"][i] for i in self.index["evidence"].get(evidence_id, [])]


def _store_from_payload(payload: dict, dataset_dir: Path) -> EvidenceStore:
    store = EvidenceStore(manifest=load_manifest(dataset_dir))
    store.activity = load_activity(dataset_dir)        # row-level indexes: cheap, always fresh
    store.observations = [observation_of(c) for c in payload["cards"]]
    store.covers = [ScopeCover(c["evidence_id"], c["captured_at"], c["system_id"],
                               frozenset(c["resource_ids"]), c["record_type"]) for c in payload["covers"]]
    store.links = [tuple(link) for link in payload["links"]]
    store.errors = [tuple(e) for e in payload["errors"]]
    return store


def load_or_build(dataset_dir: Path, image_cache: Path, path: Path, trail=None,
                  rebuild: bool = False) -> EvidenceCardStore:
    fp = fingerprint(dataset_dir, image_cache)
    if path.exists() and not rebuild:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("meta", {}).get("fingerprint") == fp and \
                    payload["meta"].get("schema_version") == CARD_SCHEMA_VERSION:
                if trail:
                    trail.write("evidence_cards", source="cache", cards=payload["meta"]["cards"])
                return EvidenceCardStore(payload, _store_from_payload(payload, dataset_dir), "cache")
            reason = "fingerprint_changed"
        except (ValueError, KeyError, TypeError) as exc:     # corrupt / partial file: rebuild
            reason = f"unreadable:{type(exc).__name__}"
    else:
        reason = "forced" if rebuild else "missing"
    store = load_evidence(dataset_dir, image_cache)
    payload = build_payload(store, fp)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(path)                                   # atomic: never leaves a half-written file
    if trail:
        trail.write("evidence_cards", source="rebuilt", reason=reason, cards=payload["meta"]["cards"],
                    parse_errors=len(store.errors))
    return EvidenceCardStore(payload, store, "rebuilt")

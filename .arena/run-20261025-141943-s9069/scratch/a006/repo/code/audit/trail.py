"""Append-only JSONL audit trail of decisions, LLM calls, approvals and denials."""
from __future__ import annotations

import json
from pathlib import Path


class AuditTrail:
    def __init__(self, path: Path | None):
        self.path = path
        self.entries: list[dict] = []

    def write(self, event: str, **fields) -> None:
        self.entries.append({"event": event, **fields})

    def flush(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="\n") as fh:
            for entry in self.entries:
                fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, default=sorted) + "\n")

"""PDF text (via pdftotext) and cached screenshot facts -> Observations.

PDFs carry a text layer, so no OCR is needed. Screenshots are extracted once by
`code/tools/extract_images.py` (vision model) into code/cache/image_facts.json; this module only
reads that cache, so pipeline runs are deterministic and need no API key.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ..aliases import RESOURCE_RE, classify_value, emails_in_text, record_type_for, system_for
from ..schema import PRESENT, Observation
from .common import record_observation

USER_TOKEN_RE = re.compile(r"\buser_\d+\b")
REFERENCE_RE = re.compile(r"\b(?:NST-\d{4}-\d{4}-\d{4}|ORD-\d{8})\b")


def pdf_text(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if exe:
        res = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=False)
        if res.returncode == 0:
            return res.stdout
    try:                                    # optional pure-python fallback
        from pypdf import PdfReader         # type: ignore
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    except Exception:
        return ""


def parse_pdf(path: Path, file_id: str, captured_at: str, reference_index: dict):
    """Each PDF concerns the resources/references it names; identity comes from its text."""
    text = pdf_text(path)
    emails = emails_in_text(text)
    users = set(USER_TOKEN_RE.findall(text))
    rids = {m.group(0) for m in RESOURCE_RE.finditer(text)}
    for ref in REFERENCE_RE.findall(text):
        rids |= reference_index.get(ref, set())
    observations = []
    retain = re.search(r"retain until\s+(\d{1,2} \w{3} \d{4})", text, re.I)
    for rid in sorted(rids):
        rtype = record_type_for(rid)
        if rid.startswith("support_") and re.search(r"attachment|\.pdf", text, re.I):
            rtype = "SUPPORT_ATTACHMENT"
        observations.append(Observation(
            evidence_id=file_id, observed_at=captured_at, captured_at=captured_at,
            system_id=system_for(rid), resource_id=rid, record_type=rtype, state=PRESENT,
            pii=bool(emails) or None, emails=set(emails), users=set(users),
            source=f"pdf:{path.name}", attrs={"retain_until": retain.group(1) if retain else None}))
    return observations, []


def parse_image_cache(cache_path: Path, manifest: dict):
    """Cached facts: {file_id: {"records": [ {resource_id, fields..., state?} ]}}."""
    if not cache_path.exists():
        return [], []
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    observations, links = [], []
    for file_id, facts in data.items():
        meta = manifest.get(file_id)
        if not meta:
            continue
        try:                                # schema check: malformed facts are never used
            from ..vision_schema import ImageFacts
            facts = ImageFacts.model_validate(facts).model_dump(exclude_none=True)
        except ImportError:
            pass                            # pydantic absent: cache was validated when written
        except ValueError as exc:
            raise ValueError(f"{file_id}: invalid screenshot facts: {exc}") from exc
        for rec in facts.get("records", []):
            obs = record_observation(rec, evidence_id=file_id, observed_at=meta["captured_at"],
                                     captured_at=meta["captured_at"], collection=rec.get("collection"),
                                     source=f"image:{meta['file_path']}")
            if obs is None:
                continue
            for key in ("emails", "users"):
                for value in rec.get(key, []) or []:
                    hit = classify_value(value)
                    if hit:
                        (obs.emails if hit[0] == "email" else obs.users).add(hit[1])
            observations.append(obs)
            for other in rec.get("related_resource_ids", []) or []:
                links.append((obs.resource_id, other, file_id))
    return observations, links

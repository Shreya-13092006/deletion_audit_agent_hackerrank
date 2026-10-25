"""One-time extraction of facts from the PNG console screenshots.

Backends (all output validated with pydantic, see audit/vision_schema.py):
  windows-ocr  (default) local Windows.Media.Ocr engine + deterministic closed-world parsing;
               writes code/cache/image_facts.json, the only file the pipeline reads.
  gemini       Gemini vision (default model gemini-3.8-flash, needs GEMINI_API_KEY)
  anthropic    Claude vision (needs ANTHROPIC_API_KEY and the anthropic SDK)
Model backends are a cross-check: they write code/cache/image_facts_<backend>.json (never the
OCR cache), keep only identifiers already known in participant data, and write a
record-by-record comparison against the OCR facts (image_facts_<backend>_vs_ocr.json).

Screenshots are ordinary admin-console pages (backup vault, connector console, search
inspector, ...). A vision model reads each one into structured records with the same field
names the other parsers emit, so the pipeline treats them like any other evidence. The
cache is committed with the code: pipeline runs never need an API key or re-bill.

Usage (from the repository root):
    python code/tools/extract_images.py [--force]                         # local OCR
    python code/tools/extract_images.py --backend gemini --allow-vision [--model gemini-3.8-flash]
    python code/tools/extract_images.py --backend anthropic --allow-vision [--model claude-opus-5-5]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import CACHE_DIR, DATASET_DIR, VISION_MODEL, VISION_THINKING  # noqa: E402
from audit.llm import LLM  # noqa: E402
from audit.parsers import load_manifest  # noqa: E402
from audit.screen_ocr import parse_screen  # noqa: E402
from audit.trail import AuditTrail  # noqa: E402
from audit.vision_schema import ImageFacts, ImageFactsCache  # noqa: E402

NULLABLE_STR = {"type": ["string", "null"]}
NULLABLE_BOOL = {"type": ["boolean", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "screen": {"type": "string"},
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string"},
                    "record_type": NULLABLE_STR,
                    "result": NULLABLE_STR,
                    "email": NULLABLE_STR,
                    "customer_reference": NULLABLE_STR,
                    "phone": NULLABLE_STR,
                    "full_name": NULLABLE_STR,
                    "enabled": NULLABLE_BOOL,
                    "restore_allowed": NULLABLE_BOOL,
                    "related_resource_ids": {"type": "array", "items": {"type": "string"}},
                    "note": NULLABLE_STR,
                },
                "required": ["resource_id", "record_type", "result", "email", "customer_reference",
                             "phone", "full_name", "enabled", "restore_allowed",
                             "related_resource_ids", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["screen", "records"],
    "additionalProperties": False,
}

PROMPT = """This is a screenshot of an internal admin console of an e-commerce company. Extract every
record row or detail panel that names a resource identifier such as account_N, search_N,
analytics_N, support_N, export_N, data_flow_N, backup_N, audit_record_N, tombstone_N,
legal_hold_N or marketing_N. For each one return exactly what is visible:
- resource_id: the identifier as printed
- record_type: one of USER_PROFILE, SEARCH_INDEX_ENTRY, ANALYTICS_PROFILE, SUPPORT_MESSAGE,
  SUPPORT_ATTACHMENT, USER_EXPORT, MARKETING_PROFILE, DATA_FLOW, BACKUP_ARCHIVE,
  SECURITY_AUDIT_LOG, LEGAL_HOLD_RECORD, ACCOUNT_TOMBSTONE, or null if unclear
- result: FOUND if the record is shown as existing, NOT_FOUND if shown as deleted/missing,
  IDENTIFIABLE if it still shows a person's email/phone/name, ANONYMIZED or REDACTED if those
  are shown removed, ACTIVE/DISABLED for connectors, BLOCKED for blocked restores; else null
- email, customer_reference (user_N), phone, full_name: as printed for that record, else null
- enabled (connectors) and restore_allowed (backups): true/false only if the screen says so
- related_resource_ids: other identifiers shown as linked to this record
Do not guess values that are not visible."""


def to_record(rec: dict) -> dict:
    out = {k: v for k, v in rec.items() if v not in (None, [], "") and k != "note"}
    if out.get("email"):
        out["email"] = out["email"].strip().lower()
    return out


def known_identifiers():
    """Closed-world vocabularies the OCR backend may map screen text onto (never extended)."""
    from audit.identity import IdentityGraph
    from audit.parsers import load_evidence
    store = load_evidence(DATASET_DIR, CACHE_DIR / "__no_image_cache__.json")
    graph = IdentityGraph.load(DATASET_DIR)
    resources = {o.resource_id for o in store.observations} | {r["resource_id"] for r in store.activity.rows}
    return resources, set(graph.by_email), set(graph.identities), store.activity.reference_index


def run_windows_ocr(png_path: Path, file_id: str) -> dict:
    """Three OCR readings with the built-in Windows engine (1x, 2x, 2x grayscale - inverted
    for dark themes); raw output cached per file so re-runs are deterministic."""
    raw_path = CACHE_DIR / "ocr_raw" / f"{file_id}.json"
    if raw_path.exists():
        return json.loads(raw_path.read_text(encoding="utf-8"))
    from PIL import Image, ImageOps, ImageStat
    script = Path(__file__).resolve().parent / "ocr_windows.ps1"
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for key in ("1", "2", "2g"):
            scale = int(key[0])
            scaled = Path(tmp) / f"{file_id}_{key}.png"
            img = Image.open(png_path).convert("RGB")
            if key.endswith("g"):
                img = img.convert("L")
                if ImageStat.Stat(img).mean[0] < 128:          # dark theme: light text on dark
                    img = ImageOps.invert(img)
            img.resize((img.width * scale, img.height * scale), Image.LANCZOS).save(scaled)
            res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                  str(script), str(scaled)], capture_output=True, text=True,
                                 encoding="utf-8", check=True)
            out[key] = json.loads(res.stdout)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return out


MODEL_BACKENDS = {"gemini": "gemini-", "anthropic": "claude-"}


def validate_model_records(raw_records: list, known) -> tuple[list, list]:
    """Closed-world check for model output, same rule as the OCR path: an identifier is kept only
    if it already exists in participant data. Unknown contacts become a note, never an identity."""
    from pydantic import ValidationError
    from audit.vision_schema import ExtractedRecord
    known_resources, known_emails, known_users, _refs = known
    records, rejected = [], []
    for raw in raw_records:
        rec = to_record(raw)
        rid = rec.get("resource_id", "")
        if rid not in known_resources:
            rejected.append(rid or "<missing resource_id>")
            continue
        email = rec.get("email")
        if email and email not in known_emails:
            rejected.append(email)
            rec.pop("email")
            rec["note"] = f"contact not in identity tables: {email}"
        user = rec.get("customer_reference")
        if user and user not in known_users:
            rejected.append(user)
            rec.pop("customer_reference")
        rel = rec.get("related_resource_ids") or []
        rec["related_resource_ids"] = [r for r in rel if r in known_resources]
        try:
            records.append(ExtractedRecord(**rec).model_dump(exclude_none=True))
        except ValidationError:
            rejected.append(f"{rid}:schema")
    return records, sorted(set(rejected))


def compare_with_ocr(model_facts: dict, ocr_facts: dict) -> dict:
    """Record-by-record comparison on the fields the pipeline uses."""
    fields = ("email", "customer_reference", "result", "record_type", "enabled", "restore_allowed")
    report = {}
    for file_id in sorted(set(model_facts) | set(ocr_facts)):
        m = {r["resource_id"]: r for r in model_facts.get(file_id, {}).get("records", [])}
        o = {r["resource_id"]: r for r in ocr_facts.get(file_id, {}).get("records", [])}
        diffs = {"only_model": sorted(set(m) - set(o)), "only_ocr": sorted(set(o) - set(m)), "field_mismatch": []}
        for rid in sorted(set(m) & set(o)):
            for f in fields:
                if m[rid].get(f) != o[rid].get(f):
                    diffs["field_mismatch"].append({"resource_id": rid, "field": f,
                                                    "model": m[rid].get(f), "ocr": o[rid].get(f)})
        report[file_id] = diffs
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["windows-ocr", "gemini", "anthropic"], default="windows-ocr",
                    help="windows-ocr: local Windows.Media.Ocr, no network (default); "
                         "gemini / anthropic: vision model via the provider API (cross-check only)")
    ap.add_argument("--allow-vision", action="store_true",
                    help="explicit opt-in required for model backends (screens contain personal data)")
    ap.add_argument("--model", default=None, help=f"model id (default for gemini: {VISION_MODEL})")
    ap.add_argument("--out", type=Path, default=None,
                    help="output file for model backends (default code/cache/image_facts_<backend>.json)")
    ap.add_argument("--force", action="store_true", help="re-extract files already in the output")
    args = ap.parse_args(argv)
    ocr_path = CACHE_DIR / "image_facts.json"
    model_backend = args.backend in MODEL_BACKENDS
    if model_backend:
        if not args.allow_vision:
            print("refusing to send screenshots to a model without --allow-vision")
            return 2
        model = args.model or (VISION_MODEL if args.backend == "gemini" else "claude-opus-5-5")
        if not model.startswith(MODEL_BACKENDS[args.backend]):
            print(f"model {model!r} does not belong to backend {args.backend!r}")
            return 2
        out_path = args.out or CACHE_DIR / f"image_facts_{args.backend}.json"
        if out_path.resolve() == ocr_path.resolve():
            print("refusing to overwrite the OCR cache with model output; adoption is a separate, reviewed step")
            return 2
        trail = AuditTrail(CACHE_DIR / f"image_extraction_trail_{args.backend}.jsonl")
        llm = LLM(CACHE_DIR / f"vision_cache_{args.backend}.json", enabled=True, trail=trail)
        if not llm.available_for(model):
            key_env = "GEMINI_API_KEY" if args.backend == "gemini" else "ANTHROPIC_API_KEY (and the anthropic SDK)"
            print(f"BLOCKED: {key_env} missing; nothing sent. Use --backend windows-ocr for local extraction.")
            return 1
    else:
        out_path, llm, model = ocr_path, None, None
    known = known_identifiers()
    facts = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    pngs = [(f, m) for f, m in sorted(load_manifest(DATASET_DIR).items())
            if m["file_path"].lower().endswith(".png")]
    for file_id, meta in pngs:
        if file_id in facts and not args.force:
            continue
        path = DATASET_DIR / meta["file_path"]
        png = path.read_bytes()
        if llm is not None:
            result = llm.json_call(model, PROMPT, SCHEMA, image_png=png, effort="medium", max_tokens=8000,
                                   thinking_level=VISION_THINKING if args.backend == "gemini" else None)
            if result is None:
                print(f"{file_id}: no result (error, refusal or incomplete); see the extraction trail")
                continue
            records, rejected = validate_model_records(result.get("records", []), known)
            screen, engine = str(result.get("screen", "")), f"{args.backend}:{model}"
        else:
            records, rejected, screen = parse_screen(run_windows_ocr(path, file_id), *known)
            engine = "windows-ocr:Windows.Media.Ocr(en-US)@1x+2x+2x-gray"
        entry = ImageFacts(file_path=meta["file_path"], screen=screen, extracted_by=engine,
                           records=records, source_sha256=hashlib.sha256(png).hexdigest(),
                           rejected_tokens=rejected)          # pydantic validation
        facts[file_id] = entry.model_dump(exclude_none=True)
        print(f"{file_id}: {len(records)} records "
              f"{[r['resource_id'] for r in records]} rejected={len(rejected)}")
    ImageFactsCache.model_validate(facts)
    out_path.write_text(json.dumps(facts, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    if llm is not None:
        llm.save()
        llm.record_usage(f"image_extraction_{args.backend}", len(pngs))
        trail.flush()
        ocr = json.loads(ocr_path.read_text(encoding="utf-8")) if ocr_path.exists() else {}
        report = compare_with_ocr(facts, ocr)
        diff_path = out_path.with_name(out_path.stem + "_vs_ocr.json")
        diff_path.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        n = sum(len(d["only_model"]) + len(d["only_ocr"]) + len(d["field_mismatch"]) for d in report.values())
        print(f"model facts: {out_path}\ncomparison vs OCR: {diff_path} ({n} difference(s)); "
              f"the pipeline still reads only {ocr_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

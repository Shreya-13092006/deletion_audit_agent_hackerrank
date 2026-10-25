# HackerRank Orchestrate - October 2026

## Ghost Data Still Exists

Build an AI agent that audits whether a user's personal data was actually deleted.

A deletion workflow may report **Complete** while data still exists in databases, logs, support attachments, exports, search indexes, archives, or backups. Sync and restore processes may also bring deleted data back.

For each request, the agent must first determine whether deletion was actually requested. It then returns `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`, reports any remaining data or recreation risk, and produces the ordered remediation and verification steps required to finish an authorized deletion safely.

Read [`problem_statement.md`](./problem_statement.md) for the complete challenge contract.

---

## Our Solution: an evidence-driven deletion audit agent

### Setup and run

You need Python 3.10 or later. `pip install -r code/requirements.txt` installs pydantic (validates the screenshot facts) and Pillow (only for re-running OCR). With the shipped caches, `output.csv` is reproduced offline.

There are two entry points. **Both write the root `./output.csv` by default**, so the last one you run decides what that file contains. Use `--out <path>` to write somewhere else.

| Command | What it is | Root `output.csv` sha256 |
|---|---|---|
| `python code/agent_main.py --no-llm` | **Proof-gated agent: this is the submitted `output.csv`.** The bounded agent loop runs over the same engine, then the proof gates (G2/G3/G4/G9). A COMPLETE answer without cited proof for every linked record and the primary account becomes INCOMPLETE, with post-remediation checks, and is flagged for review. 518 rows: 370 INCOMPLETE, 138 COMPLETE, 10 NOT_APPLICABLE. | `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37` |
| `python code/main.py` | Baseline deterministic engine, without the proof gates. **Running it overwrites `output.csv` with the baseline predictions** (355 INCOMPLETE, 153 COMPLETE, 10 NOT_APPLICABLE). The 15 cases the gates downgrade go back to COMPLETE. | `1bbba042d47fef1a8fb9fd2eae5182b113c3f8a91394ecb544f9aa4410b4b095` |

`AGENT_PROOF_DOWNGRADE=0 python code/agent_main.py --no-llm` also reproduces the engine hash (`1bbba042…b095`): the gates still run, but they only flag. The 15 cases where the two differ are listed with their evidence in `docs/reviews/recovery-artifacts/20261025-verification/changed_cases.md`.

Hash history: the engine output before the `retained_order_loaded` parser fix (`7a9683fd…ea50`) is preserved at `docs/reviews/recovery-artifacts/20261025-verification/backup/output.csv`. The proof-gated output before that fix was `1d9870ad…cfde6`. The fix adds one step to case_220 (`VERIFY_RECORD_PRESENT legal_hold_4961`) in both.

```bash
python code/agent_main.py --no-llm        # 518 cases -> ./output.csv (submitted, proof-gated; about 2 s, deterministic)
python code/main.py                       # 518 cases -> ./output.csv (baseline engine; overwrites the proof-gated file)
python code/main.py --split sample        # 32 public cases -> ./sample_predictions.csv
python code/evaluation/main.py [-v]       # run and score the sample split vs dataset/sample_output.csv
python code/evaluation/main.py --custom   # hand-built evaluation cases
python code/evaluation/agent_eval.py      # engine vs agent on the samples, tune/hold-out split
python code/evaluation/verify_output.py   # independent read-only check of ./output.csv (stdlib only; exit 1 on a hard failure)
python -m unittest discover -s code/tests -t code/tests   # 192 tests
```

**PDF text extraction:** the code uses `pdftotext` (poppler) when it is on PATH and falls back to `pypdf` if that is installed.

**Screenshots:** facts from the 11 screenshots are already extracted into `code/cache/image_facts.json`, so you don't need to re-run this. To regenerate them:
- **Local, the default:** `python code/tools/extract_images.py --force` uses the built-in Windows OCR engine (Windows only). It takes three readings per image, parses them deterministically against known identifiers, and validates the result with pydantic.
- **Gemini vision cross-check (`gemini-3.8-flash`):** set `GEMINI_API_KEY` in your environment (never in a file that is committed), then run `python code/tools/extract_images.py --backend gemini --allow-vision`. No extra package is needed; it uses Python's standard library. It writes `code/cache/image_facts_gemini.json` plus a record-by-record comparison, `image_facts_gemini_vs_ocr.json`. It never overwrites the OCR cache the pipeline reads, and keeps only identifiers already known in the data.
- **Anthropic vision (alternative):** `pip install anthropic`, export `ANTHROPIC_API_KEY`, then run `... --backend anthropic --allow-vision`.

After either one, re-run `python code/agent_main.py --no-llm`. `--no-llm` forbids model calls but still uses cached results.

### Architecture

The pipeline is sequential, modular and deterministic, in `code/audit/`:

```
Parse ─► Normalize ─► Resolve identity ─► Classify intent ─► Discover records ─►
Resolve state @ audit_at ─► Apply policy per record_type ─► Plan remediation/verification ─► Validate ─► Report
```

| Module | Responsibility |
|---|---|
| `parsers/` | Everything becomes one canonical **Observation** card (file_id, observed/captured time, system, resource, record_type, state, PII flag, identifiers, original fields). Sources covered:<br>• 4 SQL schema families (in-memory SQLite, never written)<br>• snapshot bundles, service exports and record ledgers<br>• 7 log line formats, with `*_started`/`*_completed` lines joined by `trace_id`<br>• handover text<br>• PDFs (text layer)<br>• cached screenshot facts<br>• `system_activity.csv` (claims only, plus `LINK_RESOURCE_IDENTITY`, `CLASSIFY_REQUEST`, recreation signals) |
| `aliases.py` | Alias map: `user_id/customer_reference/subject_reference/subject_ref/subject_selector/lookup_key`, emails across nine field names, `correlation_key` hashes, resource-prefix → system, and table/collection → `deletion_rules` category |
| `identity.py` | Current and historical emails (trimmed, lowercased), sha256 hashes (verified algorithm) and audit-log `email_hash` values. **Names are never used for linking** |
| `linker.py` | Exact-identifier links, decoy guard (a record naming another user_id is not linked), resource propagation, `source_resource_id` links, and connectors or backups that repopulated a linked resource |
| `state.py` | Uses only evidence available at or before `audit_at`. The latest reading wins; at one time point any primary or replica copy showing the record means present; absence by omission comes only from snapshots in scope, for never-observed resources |
| `policy.py` | Applies `deletion_rules.csv` per **record type**: DELETE, REDACT (support messages, tombstones), ANONYMIZE, RETAIN (security audit, legal hold), plus BLOCK_RESTORE and DISABLE_DATA_FLOW for recreation paths |
| `planner.py` | Findings, then remediation (flows and restores first), then verification, in table order then system and resource. Findings and COMPLETE verifications cite evidence; future steps use `""` |
| `pipeline.py` | Orchestration, plus **workflow attribution**: the profile the deletion workflow deleted just before `reported_at`, with its result matching the reported status. Used only when evidence carries no identity, and never by guessing between people |
| `intent.py` | Multilingual rules (EN/ES/PT/FR/JA/KO/…), explicit non-deletion patterns and `CLASSIFY_REQUEST` corroboration. Model fallback only for undecidable text |
| `guardrails.py`, `trail.py` | Guardrails listed below |
| `screen_ocr.py`, `vision_schema.py` | Layout-based parsing of local OCR output, accepting only identifiers that are known or agreed between readings; pydantic models for screenshot facts and the cache |
| `validate.py` | Checks the output contract before writing |

**Guardrails:**
- **PII scrubbing** happens before any model call.
- **Role capabilities:** `parser`, `resolver`, `classifier`, `planner`. `executor` is never granted.
- **Human approval:** `ApprovalGate` blocks irreversible operations without approval. The agent only *proposes* plans.
- **Audit trail:** JSONL in `code/cache/audit_trail.jsonl`.
- **Fail-safe flags:** ambiguous or unresolved identity, unknown state, no citable proof (never COMPLETE without proof), and retained records seen only later.

### Where models are used

| Need | Model | Notes |
|---|---|---|
| 11 PNG console screenshots → structured facts | **Used: local Windows OCR** (`Windows.Media.Ocr`) plus closed-world parsing and pydantic validation. Cross-check: **`gemini-3.8-flash`** (`AUDIT_VISION_MODEL`), thinking `medium`, image resolution `ultra_high`, JSON-schema output | One-time; model output goes to a separate file for review and is never read by the pipeline automatically. Ollama `llava:7b` was rejected because it risks hallucinated identifiers |
| Ambiguous request intent | **`gemini-3.5-flash-lite`** (`AUDIT_INTENT_MODEL`), thinking `minimal`, PII-scrubbed input, JSON-schema output, cached | Used only when the rules can't decide: 0 calls on this dataset. With no `GEMINI_API_KEY` set, the fail-safe applies (NOT_APPLICABLE plus a flag) |
| PDFs | none (`pdftotext`) | They have a text layer |
| SQL, JSON, logs, CSV | none | Deterministic |

### Assumptions and known limits

See `code/evaluation/evaluation_report.md` §4 and `docs/dataset-observations.md`. In summary:
- The workflow timing windows were measured on the public samples.
- Ownership may come from later evidence, while state and citations never do.
- Anonymized records in shared report windows are not attributed.
- Screenshot facts come from local OCR; identifiers are accepted only when they match known data or two OCR readings agree.
- State evidence must be at most 14 days older than `audit_at` (`AUDIT_STATE_MAX_AGE_DAYS`).
- Workflow ties decided by time alone are flagged (`ACCOUNT_WORKFLOW_TIME_ONLY_TIE`).

**Results on the 32 public samples:** status accuracy 1.000, step F1 0.971, evidence accuracy 1.000, sequence accuracy 0.688. The samples were also used for tuning, so these are not hidden-test estimates.

---

## Quick Start

Clone the repository and move into the project directory:

```bash
git clone https://github.com/interviewstreet/hackerrank-orchestrate-october26.git
cd hackerrank-orchestrate-october26
```

Start your AI coding tool from the **repository root** so it automatically reads [`AGENTS.md`](./AGENTS.md) and logs your session turns to `log.txt` in the root directory.

Build your solution in `code/main.py`, or use another language and document its setup and run command clearly in your README.

Your solution must:

- Read the input files from `dataset/`
- Generate one prediction row for every request in `dataset/deletion_requests.csv`
- Write the final predictions to `output.csv` in the repository root

Run the starter Python entry point with:

```bash
python3 code/main.py
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file for submission must be the root-level `output.csv`.


## Dataset

All participant-facing files are in `dataset/`:

| File | Contents |
| --- | --- |
| `deletion_requests.csv` | 518 requests |
| `sample_deletion_requests.csv` | 32 sample requests |
| `sample_output.csv` | Correct sample answers |
| `user_identities.csv` | Current user identities |
| `user_audit_log.csv` | Historical identity changes |
| `system_activity.csv` | Activity across services and data processes |
| `deletion_rules.csv` | Required treatment for each data category |
| `evidence_files.csv` | Manifest of supplied evidence files |
| `output.csv` | Blank output template |

Evidence is stored under `dataset/evidence/` and may include PDFs, images, logs, JSON, plain text, or SQL snapshot exports. SQL captures may contain a primary database, regional replicas, a reporting replica, or a failover replica so replication drift can be investigated directly. The `.sql` files are readable as text and executable with SQLite.

Only `deletion_requests.csv` requires answers. The other files provide evidence and context.

---

## Output

Create `output.csv` with these columns in this exact order:

```text
case_id,deletion_status,steps_json
```

Produce exactly one row per request. `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. `steps_json` is an ordered JSON array containing findings, remediation actions, and verification checks. Use an empty array (`[]`) for `NOT_APPLICABLE`. Evidence references may be a `file_id`, `activity_id`, or `audit_id`. Determine the resource state at `audit_at` from the available evidence; reported workflow statuses and operation results are claims. Use `dataset/sample_output.csv` as the format reference.

The final file must contain 518 data rows sorted by `case_id` (plus the header row). The grader parses `steps_json` as JSON, so object-key order and whitespace do not matter; array order does. Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`.

---

## Evaluation

`output.csv` will be compared with hidden canonical answers. Scoring considers:

- deletion assessment accuracy;
- current and historical identity resolution;
- discovery of remaining data and recreation risks;
- correct policy application and evidence references; and
- completeness and ordering of remediation and verification steps.

Your `code.zip` must include:

```text
code/evaluation/evaluation_report.md
code/evaluation/usage_report.md
```

- `evaluation_report.md` must cover case, row, field, and sequence accuracy, at least three additional evaluation cases created by you, failures found, and improvements made.
- `usage_report.md` must cover the final full-dataset run, including model providers and names, model calls, input and output tokens, total and average tokens per request, and estimated total and per-request cost. Include per-model and overall totals when using multiple models.

**Important:** Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout), write your complete evaluation metrics, custom evaluation test cases, and token/cost breakdowns directly inside those Markdown files, and keep prompts in source code or Markdown files. Automated code evaluation ignores raw data files (`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`), so content stored only in those formats will not be visible to the code judge or AI interviewer.

---

## Chat Transcript

This repository includes [`AGENTS.md`](./AGENTS.md), which instructs compatible AI coding tools to append conversation summaries to `log.txt` in the repository root:

| Platform | Path |
| --- | --- |
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

- Always launch your AI coding agent from the repository root (or explicitly ask it to read `./AGENTS.md` first) so every turn is logged to `log.txt` with the required `User Prompt`, `Agent Response Summary`, `Actions`, and `Context` sections.
- Upload `log.txt` directly as your `chat_transcript` submission on HackerRank.
- Do not include API keys, tokens, credentials, or secrets in prompts, code, configuration, or `log.txt`.

---

## Packaging `code.zip` and Submission

| Item | Description |
| --- | --- |
| `code.zip` | Runnable solution, prompts, configuration, `README.md`, and `evaluation/` reports |
| `output.csv` | One answer row for each of the 518 requests in `dataset/deletion_requests.csv` |
| `chat_transcript` | The root `log.txt` file generated by your coding agent |
| AI interview | Live explanation of your architecture, approach, and evaluation |

You may use any programming language, model, framework, or retrieval approach. Include clear setup and execution instructions in `README.md` inside `code.zip`.

To package `code.zip` from the repository root without bundling the dataset:

**macOS / Linux:**

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

**Windows (PowerShell):**

```powershell
Compress-Archive -Path README.md, code -DestinationPath code.zip -Force
```

When packaging `code.zip`:

- Keep your evaluation reports in `code/evaluation/` so they are bundled automatically with `code` (or add `evaluation` to the archive command above if you placed them in a top-level `evaluation/` directory).
- Do **not** include `dataset/`, virtual environments (`.venv`, `venv`, `node_modules`), or build caches (`__pycache__`). On Windows, keep `.venv` at the repository root (outside `code/`) and remove any `code/__pycache__` folders before running `Compress-Archive`.
- Do **not** include nested archives (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`) inside `code.zip` — submissions containing nested archive files will be rejected.

Before submitting, confirm that:

- `output.csv` has the exact header `case_id,deletion_status,steps_json` and contains all 518 data rows sorted by `case_id`;
- every `steps_json` value is a valid JSON array with consecutive step numbers starting at `1`;
- findings cite valid evidence IDs, and `COMPLETE` verification steps cite evidence proving the current state;
- proposed remediation and future verification steps use an empty `evidence_id` (`""`);
- `code.zip` includes your runnable code, `README.md`, `code/evaluation/evaluation_report.md`, and `code/evaluation/usage_report.md`;
- `log.txt` follows the `AGENTS.md` turn format and is uploaded to the `chat_transcript` slot; and
- no API keys, credentials, real personal data, or sensitive configuration values are included.

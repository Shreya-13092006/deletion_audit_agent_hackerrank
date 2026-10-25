# Master Project Prompt — Ghost Data Still Exists (deletion-audit agent)

_Last updated: 2026-10-25T00:30Z · Interview status: in progress (MVP built, accuracy round 2 done)_

## 1. Mission
Build a terminal-runnable deletion-audit agent for HackerRank Orchestrate (October 2026). For each of the 518 requests in `dataset/deletion_requests.csv` it must decide whether the text actually asks for deletion. For real deletion requests it resolves current and historical identifiers, reconstructs the true state of every relevant resource at `audit_at` from the evidence, applies `deletion_rules.csv`, and outputs `COMPLETE` / `INCOMPLETE` / `NOT_APPLICABLE` with an ordered `steps_json`. Winning means a high score from the hidden-answer grader on status, records, evidence and ordering, plus a strong evaluation report, a clear usage/cost report and a convincing AI interview.

## 2. Hard constraints
| Constraint | Value | Status | Source |
|---|---|---|---|
| Deadline | Not configured in repo | Open | AGENTS.md §3 |
| Submission format | `code.zip` (code, prompts, README, `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`), root `output.csv` (518 rows, sorted by case_id), `log.txt` as chat_transcript, AI interview | Confirmed | README.md, problem_statement.md |
| Rules / prohibited | Use only `dataset/` data; no organizer-only files, hardcoded labels or case-family shortcuts; secrets only via env vars; log every turn to `log.txt`; no dataset, venvs or nested archives in the zip | Confirmed | AGENTS.md §4, §6.7, §6.9 |
| Language | Any; Python suggested (`code/main.py`, currently empty). Local Python 3.11.9 | Confirmed | README.md, local check |
| Team / hours / skills | Unknown | Open | — |
| Hardware / budget | Unknown (LLM API access and budget not stated) | Open | — |
| Deployment restrictions | None beyond "runnable from terminal", deterministic where possible | Confirmed | AGENTS.md §6.7 |

## 3. Problem and I/O contract
**Input** (`deletion_requests.csv`): `case_id,email,requested_at,reported_status,reported_at,audit_at,request_text`. The email can be current or historical. `reported_status` is only a claim (COMPLETE 254 / PARTIALLY_COMPLETE 152 / NOT_STARTED 112). `request_text` is multilingual (Spanish seen in samples).

**Context files:**
- `user_identities.csv`: 850 users, with user_id, name, email, phone, email_hash and updated_at.
- `user_audit_log.csv`: 306 changes to identity fields.
- `system_activity.csv`: 4,011 global events (INDEX_RECORD, sync, export, backup, restore and others) with source/target system, resource_id, reported_result and details. These are claims, and decoys are included.
- `deletion_rules.csv`: 15 rules by data category. DELETE: USER_PROFILE, SECONDARY_IDENTIFIER, SEARCH_INDEX_ENTRY, CACHE_ENTRY, SUPPORT_ATTACHMENT (subject-only), USER_EXPORT, MARKETING_PROFILE. REDACT: SUPPORT_MESSAGE (shared context), EMAIL_DELIVERY_LOG (contains email), ACCOUNT_TOMBSTONE (keep user_id only). ANONYMIZE: ANALYTICS_PROFILE, PRODUCT_TELEMETRY. RETAIN: SECURITY_AUDIT_LOG (within retention), LEGAL_HOLD_RECORD (active hold), BACKUP_ARCHIVE (restore can be blocked).
- `evidence_files.csv`: 94 files with file_id, path, origin and captured_at. The files are 24 SQL snapshots (primary, regional, reporting and failover replicas), 26 logs, 28 JSON, 1 TXT, 11 PNG screenshots and 4 PDFs. The manifest doesn't say which case a file belongs to.

**Output** (`output.csv` at the repo root): `case_id,deletion_status,steps_json`. Each step has the fields `{step_no, phase, system_id, resource_id, operation, state, evidence_id}`.
- Phase order is FINDING, then REMEDIATION, then VERIFICATION. Within a phase, sort by the operation-table order, then `system_id`, then `resource_id`.
- COMPLETE cases contain only verification steps, and each cites evidence.
- INCOMPLETE cases contain findings (with evidence), then remediation and verification (both with `evidence_id` set to "").
- NOT_APPLICABLE cases use `[]`.
- Only evidence captured at or before `audit_at` may be cited.

**Sample answers (32):** 22 INCOMPLETE, 10 COMPLETE, 0 NOT_APPLICABLE. Cases have 1–14 steps. Systems seen: account_service, search_service, support_platform, analytics_platform, security_service, integration_service, backup_service, export_service and identity_service.

**Edge cases:** historical emails, phone and name changes, email hashes, evidence captured after `audit_at`, replica drift, sync or restore that recreates deleted data, tombstones, retained security and legal-hold records, decoy activity for other users, and non-deletion requests (access, correction, export, opt-out).

## 4. Judging and evaluation
**Confirmed:** `output.csv` is compared with hidden canonical answers on status accuracy, identity resolution, discovered records and risks, cited evidence, policy decisions, and step completeness and order (problem_statement.md). Weights are unknown. The evaluation report must cover case, step, field and sequence accuracy, at least three custom cases, and the failures found with the improvements made. Plus the AI interview.
**Local measurement:** score against `sample_output.csv` (32 cases). The scorer goes in `code/evaluation/main.py`.

## 5. Differentiator
_TBD._ Leading hypothesis: a deterministic evidence-graph engine (parse every evidence format into normalized resource-state facts, with time-aware resolution at `audit_at`) and LLMs only where needed (multilingual intent, OCR or vision on PNGs and PDFs). That gives high accuracy, reproducibility and near-zero token cost.

## 6. Scope
- **MVP:** End-to-end `code/main.py` that writes 518 valid rows. It covers intent classification, identity resolution, evidence parsing of SQL, JSON, logs and TXT, rule application, and step generation with correct ordering. A local scorer runs on the 32 samples.
- **Essential:** Image and PDF extraction, sync and restore risk detection, replica drift, time cutoff, the evaluation and usage reports, the README, and packaging.
- **Stretch:** TBD
- **Non-goals:** TBD

## 7. Architecture
**Implemented** in `code/audit/` (see README "Our Solution"):
Parse → Normalize (alias map) → Resolve identity → Classify intent → Discover (exact-identifier links, trace joins, source_resource_id, recreation links, workflow attribution) → Resolve state at audit_at → Policy per record_type → Plan → Validate → Report.
It is deterministic Python stdlib code. The model is used only for screenshot extraction (cached) and the intent fallback (0 calls needed). Guardrails: PII scrub, RBAC capabilities, approval gate, JSONL trail, fail-safe flags.

**Agent loop (ADR-002, 2026-10-25):** `code/agent_main.py` + `code/audit/agent/`:
- a bounded gap-driven orchestrator over read-only engine tools
- rule planner by default (Gemini opt-in, validated)
- gates G1–G8 with parity fallback to the engine
- evidence-card store `code/cache/evidence_cards.json` (fingerprinted, indexed) and per-case cards `code/cache/case_cards.json`

Output is identical to `code/main.py`. See `docs/agent-loop-plan.md`.

## 8. Verified technical facts
| Fact | Source | Checked |
|---|---|---|
| 518 eval cases, 32 sample cases with answers, 94 evidence files | dataset/ | 2026-10-24 |
| Starter `code/main.py` and `code/evaluation/main.py` are empty | repo | 2026-10-24 |
| Local Python 3.11.9 | `python3 --version` | 2026-10-24 |
| Eval reports go in `code/evaluation/`; the code judge ignores .csv/.json/.sql/.log content | README.md | 2026-10-24 |
| Full dataset findings (schemas, linkage keys, gold-answer patterns) are in `docs/dataset-observations.md` | dataset inspection | 2026-10-24 |
| email_hash = sha256(lowercased email); 100 of 518 request emails are historical only | user_identities.csv, audit log | 2026-10-24 |
| All 24 SQL files load in stdlib sqlite3; replica drift confirmed (account_994) | evidence/databases | 2026-10-24 |
| PDFs have a text layer (pdftotext available); 11 PNG console screenshots need vision/OCR | evidence/documents, images | 2026-10-24 |
| About 10 non-deletion requests in the eval set (matches 10 CLASSIFY_REQUEST activities) | deletion_requests.csv | 2026-10-24 |

## 9. Assumptions
| Assumption | Risk if wrong | How to verify |
|---|---|---|
| Most decisions can be derived deterministically from the structured evidence | Over-investing in rules if the cases need judgment | Profile evidence against the sample answers |
| Gold evidence_id = latest qualifying file at or before audit_at that contains the fact | Evidence-field accuracy loss | Test the tie-break rule on the 32 samples |

## 10. Open questions
| # | Question | Why it matters | Priority |
|---|---|---|---|
| 1 | Submission deadline (with time zone) | Drives scope and milestones | P0 |
| 5 | Should the Anthropic vision backend still be run to cross-check the local OCR facts? (local OCR is in use; the key is not available) | Second opinion on 26 screenshot records | P2 |
| 2 | Team size, hours available, skills | Scope and ownership | P0 |
| 3 | Which LLM providers and keys are available, and the budget | Architecture, plus the usage report | P0 |
| 4 | Weighting between automated score and interview/report | Where to spend effort | P1 |

## 11. Recommendations and trade-offs
| Decision | Chosen | Alternatives | Rationale |
|---|---|---|---|
| Language | Python (recommended) | TS, other | Starter layout, stdlib sqlite3 for the .sql snapshots, Python 3.11 is installed |
| Models | Anthropic API, claude-opus-5-5 (user choice 2026-10-24) | Haiku/Sonnet 5.5, local OCR/Ollama | Cached screenshot extraction plus intent fallback; the key is read from ANTHROPIC_API_KEY |
| Screenshots | Local Windows OCR, three readings, closed-world parsing, pydantic validation (2026-10-25) | Anthropic vision (blocked: no key); Ollama llava:7b (hallucination risk); Tesseract (not installed) | Deterministic, offline, never invents identifiers |
| State freshness | Readings older than 14 days before audit_at don't establish state | No horizon | Gold citations are ≤5.6 days old; sample results identical for 7–60 days |
| Absence by omission | Only for never-observed resources in in-scope snapshots | Every in-scope snapshot | Bundles contain subject-specific records only; the broader rule cost 22% status accuracy |
| Ownership vs state time | Ownership from any evidence; state and citations only at or before audit_at | Strict cutoff for both | Gold answers include resources identified only by later evidence |
| Unidentifiable deleted accounts | Workflow attribution (reported_at window, matching result↔status), one-to-one | Leave unresolved | 14/17 correct on samples; ties flagged |

## 12. Implementation plan
_TBD after the readiness checklist passes._

## 13. Demo story
_TBD._

## 14. Risks and fallbacks
| Risk | Likelihood | Impact | Mitigation / fallback |
|---|---|---|---|
| Only 32 labeled samples, so overfitting is likely | High | High | Rules derived from policy semantics, not sample IDs; custom cases |
| Images and PDFs hold key facts | Medium | Medium | Vision LLM or OCR, with results cached |

## 15. Decision log
- 2026-10-25T03:10Z — ADR-002 implemented:
  - agent loop + evidence/case JSON cards + gates
  - hash-neutral fixes: `query` alias, retention/hold condition check (flag only), stored-hash cross-check, Anthropic try/except, `llm_unavailable` event
  - Agent = engine on every case: 518/518 parity, sha256 `7a9683fd…ea50` on two runs, 0 unsupported claims, 0 fallbacks
  - Tests: 94 in the Linux VM (the only 2 errors are pydantic missing); **109/109 OK on the user's Windows Python**
  - Starter files untouched
- 2026-10-24T14:10Z — Created from problem_statement.md, README.md, AGENTS.md and a dataset profile.
- 2026-10-25 — Parser fix: the log event `retained_order_loaded` now becomes a legal-hold presence reading (trace subject via subject_ref). Candidate output bf634e2c... adds VERIFY_RECORD_PRESENT legal_hold_4961 to case_220 only; samples unchanged (22/32; the other 10 are not discoverable or ties). Awaiting approval to replace root output.csv.
- 2026-10-25 — Snapshot-omission policy adopted as flag-only. Undeclared-scope omission counts as absence only with four conditions: system rows in the file, 14-day window, requester's other records in the capture, no other reading of the target. Single-system snapshots such as evidence_54 are accepted without the requester condition. FAILED-claim plus omission-only absence goes to review (case_58, 155, 157, 162, 260, 462), never downgraded. output.csv unchanged, 1d9870ad...cfde6.
- 2026-10-25T00:30Z — Accuracy round 2:
  - Screenshots extracted with local Windows OCR (Anthropic vision blocked: no key or SDK; llava:7b rejected for hallucination risk). Facts validated with pydantic.
  - Workflow attribution: co-occurrence tie-break and the same-system rule. Time-only ties are flagged.
  - 14-day freshness horizon for state evidence.
  - Samples: F1 0.958→0.971, sequence 0.625→0.688. 59 tests and 6/6 custom cases pass. The eval set has 0 empty or unproven cases.
- 2026-10-24T17:30Z — MVP implemented and verified. Samples: status 1.000, step F1 0.958, evidence 1.000, sequence 0.625; 48 tests and 5/5 custom cases pass; output.csv has 518 rows, deterministic, 0 model calls. Screenshots pending an API key.
- 2026-10-24T14:40Z — Deep dataset inspection; added docs/dataset-observations.md. NOT_APPLICABLE presence confirmed (about 10 cases). Leading architecture: deterministic observation-normalization engine, with an LLM only for intent and the 11 screenshots.

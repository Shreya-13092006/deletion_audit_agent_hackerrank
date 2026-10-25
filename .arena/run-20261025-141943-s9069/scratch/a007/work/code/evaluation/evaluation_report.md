# Evaluation Report — Ghost Data Still Exists

All numbers come from real runs on 2026-10-25. Current state:
- `python code/agent_main.py --no-llm` produces the submitted `output.csv` (518 cases). Two full runs give a byte-identical file, sha256 `bf634e2c…0e37`.
- `python code/main.py` runs the baseline engine without proof gates (sha256 `1bbba042…b095`).
- `python code/evaluation/main.py` scores the sample split against `dataset/sample_output.csv`; `--custom` runs the hand-built cases.
- `python code/evaluation/verify_output.py` is the independent read-only verifier (standard library only). The submitted output has 0 hard failures and 1 warning, a category conflict in case_34 (see §10). The gold samples have 0 failures and 0 warnings.
- `python -m unittest discover -s code/tests -t code/tests`: 192 tests, all passing. Earlier sections quote the count at their time (59 in §3, 139 in §8).

The final run made no model calls (see `usage_report.md`).

> **These are not hidden-test estimates.** The 32 public samples were used for development *and* for this measurement: the workflow timing windows and the freshness horizon were checked against them. Expect lower accuracy on the hidden answers, especially for cases that depend on workflow attribution (flagged in the trail).

## 1. Metrics on the 32 public sample cases

| Metric | Previous report | **Now** |
|---|---|---|
| Case-level status accuracy | 1.000 | **1.000** (32/32) |
| Step precision / recall / F1 (all 7 fields) | 0.978 / 0.938 / 0.958 | **0.995 / 0.948 / 0.971** |
| Step-key F1 (ignores evidence_id) | 0.958 | 0.971 |
| Evidence accuracy (on key-matched steps) | 1.000 | 1.000 |
| Sequence accuracy (whole array identical) | 0.625 (20/32) | **0.688** (22/32) |

**Field accuracy** (aligned by `step_no`):

| step_no | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 0.953 | 0.953 | 0.896 | 0.891 | 0.896 | 0.896 | 0.948 |

**Eval split** (518 cases, no gold available):
- 355 INCOMPLETE, 153 COMPLETE and 10 NOT_APPLICABLE.
- 0 contract violations. Before this round, 2 cases had empty `steps_json` and 9 had no citable proof; both are now 0.

## 2. Sample mismatch analysis (12 cases whose step sequence was wrong at the start of this round)

| Case | Missing | Extra | Root cause (verified in evidence) | Outcome |
|---|---|---|---|---|
| case_03 | VERIFY_ANONYMIZED analytics_9406 | — | The only reading has `lookup_key=null` and all identifiers null. The anonymize activity falls in a window shared with case_44, and both appear in evidence_94 | **Unresolved** (true tie) |
| case_04 | VERIFY_ABSENT account_004 | — | `account_004` appears in no evidence file, no activity row and no screenshot | **Unresolved** (not discoverable) |
| case_11 | — | VERIFY_ANONYMIZED analytics_9447 | Identity-less anonymize activity was attributed although evidence already identifies the subject's analytics profile (`analytics_2034`) | **Fixed**: same-system rule |
| case_18 | VERIFY_PRESENT audit_record_6645 | — | The record appears in no evidence, activity or screenshot (OCR text checked) | **Unresolved**, never invented |
| case_20 | VERIFY_PRESENT audit_record_5569 | — | Same as case_18 | **Unresolved**, never invented |
| case_21 | VERIFY_ANONYMIZED analytics_5335 | — | Identity-less; the window is shared by 6 cases and case_21 vs case_23 both co-occur in evidence_92 | **Unresolved** (true tie) |
| case_23 | VERIFY_ABSENT account_410 | VERIFY_ABSENT account_9155 | Two FAILED account deletes in one report slot with equal evidence support. Time proximity picks wrong | **Flagged** `ACCOUNT_WORKFLOW_TIME_ONLY_TIE` |
| case_25–27 | VERIFY_ANONYMIZED analytics_1895 / 4566 / 4574 | — | Same as case_21 (shared windows, equal support in evidence_92) | **Unresolved** (true ties) |
| case_28 | VERIFY_ABSENT account_5482, VERIFY_ANONYMIZED analytics_6077 | VERIFY_ABSENT account_7012 | Account tie with case_29 was decided by time. Evidence co-occurrence now ranks before time | **Account fixed**; analytics still a tie |
| case_29 | VERIFY_ABSENT account_7012 | VERIFY_ABSENT account_5482 | Mirror of case_28 | **Fixed** |

There were no ordering-only or wrong-evidence mismatches: every failure was a missing or extra step.

**Security records (case_18, 20):** searched all 94 evidence files, `system_activity.csv` and the OCR text of all 11 screenshots. Neither `audit_record_6645` nor `audit_record_5569` appears anywhere in participant data, so nothing is emitted for them.

**Workflow ties:** 64 eval cases carry `ACCOUNT_WORKFLOW_TIME_ONLY_TIE`. I tried strict abstention on ties. It left 132 cases (eval plus samples) without a primary account and lowered sample F1 (0.971 → 0.968), so ties are decided by time proximity, which was 82% correct on the samples, and flagged.

## 3. Additional evaluation cases (`code/evaluation/custom_cases.py`): 6/6 pass

| # | Scenario | Proves | Expected |
|---|---|---|---|
| C1 | Old email with mixed case and a space; the only copy is keyed by sha256(old email) | Historical identity and hash link; per-record-type DELETE | INCOMPLETE, 4 steps |
| C2 | Primary deleted, read replica still serves the profile | Replica drift | INCOMPLETE, 3 steps |
| C3 | Compliant at audit; a search hit appears only in later evidence | Audit cutoff | COMPLETE, 2 cited steps |
| C4 | A connector repopulates search and a backup can restore | Recreation paths and the disable/block-first order | INCOMPLETE, 10 steps |
| C5 | "Remove me from marketing lists only" | Non-deletion trap | NOT_APPLICABLE |
| C6 | **New:** a months-old reading of an export, plus a fresh account reading | Freshness horizon | COMPLETE, 1 step |

**59 regression tests.** 11 are new this round:
- pydantic schema rejection, and validation of the shipped cache
- OCR confusion repair limited to known identifiers
- two-reading agreement for unknown identifiers
- decoy row contact isolation
- freshness horizon
- co-occurrence tie-break, the same-system rule and the time-only tie flag
- a cited screenshot finding

## 4. Changes this round (sample split)

| Change | Status | Step F1 | Seq. |
|---|---|---|---|
| Start of round | 1.000 | 0.958 | 0.625 |
| Workflow attribution: evidence co-occurrence ranks before time proximity; never attribute a second identity-less record of a system the evidence already identifies | 1.000 | **0.971** | **0.688** |
| Screenshots integrated (local OCR, see §5). Two old screens then leaked into later cases (case_07 `object_19` from February, case_17 `tombstone_17` from March) | 1.000 | 0.961 | 0.625 |
| **Freshness horizon:** readings older than 14 days before `audit_at` don't establish state (gold citations are ≤5.6 days old). Sample results are identical for 7–60 days; on the eval split the horizon changed 2 rows | 1.000 | **0.971** | **0.688** |

Effect of the screenshots on the eval split: the 11 early cases each screenshot was captured for now get cited findings. They are case_34 (account_5762 still active), case_35 (search_428), case_39 (active connector data_flow_1121), case_45 (6 retained audit records), case_46 (redacted tombstone), case_50 (identifiable analytics), case_52 (export_1260), case_53 (support_1034), case_55 (restore risk backup_9287), case_61 (attachment object_19) and case_63 (marketing_001).

## 5. Screenshot extraction

**Blocker:** the Anthropic vision backend can't run here, because there is no `ANTHROPIC_API_KEY` and no `anthropic` package. It remains available behind `--backend anthropic --allow-vision`.

**Local alternatives investigated:**
- **Windows built-in OCR (`Windows.Media.Ocr`)** was chosen. It is deterministic, offline and needs no key.
- **Ollama `llava:7b`** (installed) was rejected: a 7B generative model is likely to hallucinate identifiers, which contradicts "never invent identifiers".
- **Tesseract** isn't installed.

**Method:**
1. Three OCR readings per image: 1×, 2× and 2× grayscale (inverted on dark themes).
2. Deterministic, layout-based parsing: table rows are rebuilt from word coordinates.
3. Closed-world validation:
   - Emails and user_ids must exist in the identity tables. OCR confusions (`gmaiI`→`gmail`, `user_ll`→`user_11`) are repaired only to a unique known value.
   - Resource ids must be known from other evidence or activity, or read identically by at least two readings.
   - A row showing a contact that isn't in the identity tables is never attached to a subject and is recorded as a note.
4. Every record and the whole cache are validated by **pydantic** models (`code/audit/vision_schema.py`), both when written and when the pipeline reads them.

Raw OCR output is cached in `code/cache/ocr_raw/` for reproducibility.

**Extraction results:** 26 records from 11 screens. 10 tokens were rejected, all contacts or user_ids not in the identity tables (staff and decoy addresses such as `g.silva76.jr@gmail.com` and `sj.park@naver.com`). Every OCR misread of a known identifier (`backup_92gI`, `gmaiI`, `user_ll`) was repaired to a unique known value or settled by agreement between readings.

## 6. Remaining uncertainties

- **Workflow attribution is a heuristic grounded in activity timing.** 252 eval cases use it for the primary account, and 64 of those were decided by time alone. A wrong pick yields one extra and one missing verification step.
- **8 sample steps are unrecoverable** without inventing data: 6 anonymized analytics records in shared windows, 2 security records absent from all evidence. The same pattern will recur on the hidden set.
- **OCR depends on Windows.** On macOS or Linux, the shipped cache (`code/cache/image_facts.json` plus `ocr_raw/`) is read as-is. Re-extraction there needs the Anthropic backend.
- **case_63:** `marketing_001` is catalog-linked to the subject, but its screen shows another, unregistered contact (`RECORD_SHOWS_OTHER_CONTACT`). It's treated as the subject's remaining record and flagged for review.
- **Freshness horizon (14 days):** a stale reading leaves a resource's state UNKNOWN. Retained records then become blank post-remediation checks, and other records are omitted with a `STATE_UNKNOWN` flag (84 eval cases have at least one).

## 7. Agent loop (ADR-002, `code/agent_main.py`)

Design and rationale: `docs/agent-loop-plan.md`. Full generated table: `code/evaluation/agent_evaluation.md`
(`python code/evaluation/agent_eval.py`).

A bounded, gap-driven orchestrator now runs every case:
- **The planner** picks read-only tools from the case's open investigation gaps (identity → discovery → links → intent → account → state → replica / sync / restore / retention → verify).
- **Tools** wrap the engine functions above, so there is no second implementation of any rule.
- **Gates G1–G8** (contract, citation time, claim support, completion, not-applicable, no mutation, model output, parity with the engine) decide what is written.

Results from runs on 2026-10-25:

| Check | Engine (`main.py`) | Agent (`agent_main.py`, rule planner) |
|---|---|---|
| Samples: status / step F1 / evidence / sequence | 1.000 / 0.971 / 1.000 / 0.688 | 1.000 / 0.971 / 1.000 / 0.688 |
| Hold-out 8 (every 4th sample, fixed before agent work): status / F1 / sequence | 1.000 / 0.965 / 0.625 | 1.000 / 0.965 / 0.625 |
| Eval `output.csv` sha256 | `7a9683fd…ea50` | `7a9683fd…ea50` (two runs, identical; case cards identical too) |
| Parity diffs / fallbacks / budget exhausted (518) | — | 0 / 0 / 0 |
| Unsupported-claim rate (cited steps lacking a matching evidence fact) | — | 0 (samples: 0/68) |
| Tool calls per case / tool-use effectiveness | — | 8.6 / 1.000 |
| Contradictions surfaced (518) | — | 163 status-vs-findings, 69 claim-vs-evidence (workflow said DELETE succeeded, a later reading shows the record), 11 primary-vs-replica (e.g. `account_994` missing from primary, present in read replica), 3 found/not-found flips |
| Human-review queue (518) | — | 65 cases (64 time-only workflow ties, 1 record showing another contact) |
| Model calls | 0 | 0 |

**Agent custom cases (all pass):**
- **C7:** the workflow claims a DELETE succeeded, but a later reading shows the profile is still there → INCOMPLETE plus a claim-vs-evidence contradiction.
- **C8:** a security audit record whose retention period has lapsed is kept but flagged for human review, not destroyed automatically.
- **C9:** budget exhaustion falls back to the engine decision, flagged.

**What the loop does not change:** the 10 remaining sample misses (§2) have no deciding evidence, so the agent reproduces them instead of guessing. Tool-use effectiveness is 1.000 with the rule planner by construction, because it only runs tools for open gaps. The metric exists to compare model planners: an offline test with a planner that picks tools in reverse order gives identical decisions.

**Failures found while building it, and fixed:**
- The first version never opened the verify gap. The parity gate caught it: 508 fallbacks, with the output still correct.
- Replica drift went undetected because a record missing from the primary table leaves no observation. The check now compares the genuine primary/replica tables inside each snapshot file through the evidence-card index.
- A synthetic custom case passed through a fallback; it is now required to be decided by the agent.

**Failures found by the first Gemini planner run (user's Windows machine), and fixed:**
- **PDF evidence silently lost (critical).** That PowerShell session had neither `pdftotext` nor `pypdf`. All 4 PDFs parsed as empty text with no error, and engine and agent *both* dropped to status 0.969, F1 0.957, evidence 0.994, sequence 0.656 (case_07 flipped to COMPLETE). Reproduced exactly here by disabling PDF text.
  - PDF text is now pinned in `code/cache/pdf_text.json` (keyed by name + sha256) and read first on every platform.
  - A PDF with no text is now a parse error.
  - `agent_main.py` prints a WARNING and exits non-zero on parse errors.
  - With no extractor installed, the pipeline now gives the full baseline (1.000 / 0.971 / 1.000 / 0.688).
- **Planner answers wrongly rejected.** For case-level gaps the schema's placeholder target `"none"` was treated as an invalid handle, which caused 110 needless fallbacks. Fixed, with a regression test.
- **No retry on rate limits.** 11 transient HTTP errors (429/5xx) fell straight back to the rule planner. They are now retried twice (2 s, 6 s; `AUDIT_LLM_RETRY_DELAYS`) and the status code is logged.

Throughout, parity held (0 diffs), so every answer still matched the engine. The PDF failure was an input problem upstream of both paths.

## 8. Proof gates and corroboration (2026-10-25)

**What changed:**
- **G3 (claim support)** used to check only that a cited file mentions the resource. It now recomputes, from the evidence cards, that the cited file shows the state the step claims (PRESENT / ABSENT / ACTIVE / DISABLED / BLOCKED, or identifiers visible / removed), that the reading is at or before `audit_at` and within the 14-day freshness horizon, that no other copy in the same snapshot contradicts it (any copy present = present), and that no later reading before `audit_at` supersedes it. Stale, post-cutoff, unparsed or unrelated evidence is never proof.
- **New G9 (completion proof)**, for COMPLETE answers: every linked record must have a cited step with its policy's final verification, or a recorded reason (`already_absent`, `no_policy_rule`, or `only_later_evidence` for a non-primary record whose only evidence postdates the cutoff, which the contract says must not change the answer). Active flows/backups, unknown PII, missing retained records, stale readings, wrong treatments, unresolved contradictions on cited records, and an **unproven primary account** all fail.
- **Fail-safe:** a COMPLETE answer that fails G2/G3/G4/G9 becomes INCOMPLETE. Every treated record becomes a post-remediation check (empty evidence), with no invented findings. It is flagged `AGENT_PROOF_DOWNGRADE:<gate>` and sent to review. The engine fallback answer is re-checked the same way instead of being trusted. An INCOMPLETE answer with an unsupported citation is flagged `AGENT_UNSUPPORTED_CLAIM`. `AGENT_PROOF_DOWNGRADE=0` reproduces the old output.
- **New `corroborate_evidence` tool:** opened for every contradiction and for records read by more than one file at their latest time. It attaches all readings with provenance and marks the conflict `unresolved` when independent files disagree at the same time. A workflow SUCCESS claim with no later reading is now recorded as `claim_unverified`. It is `unresolved` when the evidence before the claim shows the non-compliant state, or nothing.
- **The loop** stops with a safe fallback if a tool call makes no progress.

**Results (all non-billable, 0 model calls):**

| Check | Result |
|---|---|
| Unit tests | 139 OK (115 before + 24 new: proof gates, fail-safe, corroboration, 5 uncovered record types, phone never links, provenance of conflicting cards) |
| Custom cases | engine C1–C6 6/6; agent C7–C9 3/3 |
| Samples, engine and agent | 1.000 / 0.971 / 1.000 / 0.688, unchanged; hold-out 8: 1.000 / 0.965 / 0.625, unchanged; 0 sample downgrades |
| Engine `code/main.py` on 518 | sha256 `7a9683fd…ea50`, identical to the baseline |
| Agent `code/agent_main.py` on 518, two runs | sha256 `1d9870ad…cfde6` both times; case cards byte-identical. _Note: current submitted `output.csv`: `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37`, after the `retained_order_loaded` parser fix added one step to case_220._ |
| Agent with `AGENT_PROOF_DOWNGRADE=0` | `7a9683fd…ea50`, the baseline |
| Changed cases vs baseline | 15, all COMPLETE → INCOMPLETE by G9 `primary_account_unproven` (list: `docs/reviews/recovery-artifacts/20261025-verification/changed_cases.md`) |
| G3 failures in the final answers | 0 of 1,136 citations |
| Unresolved contradictions (518) | 32, all `claim_unverified` on DELETE_RECORD; 26 in INCOMPLETE cases and 6 in downgraded cases. No same-time cross-file conflicts found |
| Fallbacks / parity diffs (pre-downgrade) / budget exhausted / no-progress stops | 0 / 0 / 0 / 0 |
| Tool calls per case / effectiveness | 8.8 / 1.000 (corroboration: 5 of 5 sample calls closed their gap) |
| Review queue (518) | 106 (was 65) |

**The 15 downgrades:** in each case the subject's primary account has no reading visible at `audit_at`. Its only readings are in files captured after the cutoff (evidence_01/06/12/17/21/31). The workflow's DELETE_RECORD result for that account was FAILED or PARTIAL in 9 of them and SUCCESS (an unverified claim) in 6. The old answer was COMPLETE because the account check was a future-only step, which a COMPLETE answer silently drops. No public sample has this pattern, so whether the hidden answers treat these cases as COMPLETE or INCOMPLETE is **unknown**. The change follows the rule "never COMPLETE without proof", not a measured score gain.

**Kept as a non-blocking note:** 7 COMPLETE cases in which no primary account was identified at all. Sample case_04 has the same pattern, and its gold answer is COMPLETE (its account appears in no participant file), so failing these would contradict the only gold evidence.

## 9. Ownership vs state, per step (2026-10-25)

Every step now answers two questions separately, recorded on its case card (`step_audit`):
- **Ownership:** how the resource is tied to the requester. The tiers are `proven` (an identifier or resource link at or before the cutoff), `proven-later` (an identifier only in later evidence), `inferred` (workflow attribution) and `contested` (an attribution decided by time alone).
- **State:** what proves the state at `audit_at`. The bases are `direct`, `omission` (with the snapshot scope: `declared`, or `inferred` / `targeted`) and `future`.

Tiers describe the basis; they don't invalidate steps. The only hard rule is **G10**: a FINDING needs `proven` ownership. Inferred verification steps are kept. Omission citations without a declared scope are flagged (`OMISSION_SCOPE_NOT_EXHAUSTIVE`), never silently trusted, and never change the output. Evidence gaps (`primary_account_not_identified`, `no_security_audit_record`, `workflow_tie`, `account_time_only_tie`, `retained_record_unreadable`) live on the case card only, not in `output.csv`.

| Check | 518 eval cases | 32 samples |
|---|---|---|
| Steps by ownership tier | proven 2,693 · proven-later 206 · inferred 197 · contested 64 | proven 159 (159/159 match gold) · proven-later 8 (8/8) · inferred 16 (16/16) · contested 1 (0/1, case_23) |
| G10: findings without proven ownership | **0** of 722 findings | 0 |
| Steps by state basis | direct 1,059 · omission 50 · future 2,051 | direct 65 · omission 3 · future 116 |
| Omission citations without a declared scope | **33**, all in COMPLETE cases, all replica/failover files holding ≤5 records of the system (flagged, output unchanged) | 2: case_01 and case_02 on evidence_54. The gold answers cite exactly these as COMPLETE proof. |
| Evidence gaps (case cards) | workflow_tie 261 · retained_record_unreadable 126 · no_security_audit_record 83 · account_time_only_tie 64 · primary_account_not_identified 23 | see `agent_evaluation.md` |
| Missed gold steps, by reason | n/a (no gold) | 10 = **3 not discoverable** (case_04, 18, 20) + **7 ties** (case_03, 21, 23, 25–28) + **0 parser/search errors** |

`output.csv` is unchanged (sha256 `1d9870ad…cfde6`, two runs, byte-identical case cards; _note: current submitted `output.csv`: `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37`, after the `retained_order_loaded` parser fix added one step to case_220_). The 33 inferred-scope COMPLETE cases are an open decision. Treating them as non-exhaustive would downgrade them, and the same rule would downgrade gold-COMPLETE samples case_01 and case_02. They are therefore reported, not changed.

**Snapshot-omission policy (added 2026-10-25, flag-only).** Absence by omission from a snapshot without a declared scope is accepted only when four conditions hold:
- the file holds records of that system in some copy
- it was captured within 14 days before `audit_at`
- the requester's other records appear in the same capture
- no evidence anywhere reads the target resource

A snapshot dedicated to that one system cannot contain the requester's other records, so it is accepted on the other three conditions (`accepted_single_system_snapshot`). That is how gold case_01/02 use `evidence_54`. Results on 518 cases: 33 accepted, 17 declared scope, **0 failing the policy**.

A FAILED deletion claim whose absence rests only on such an omission is recorded as a `failed_claim_vs_omission` conflict (`review_required`) and sent to review, never downgraded. That applies to exactly **case_58, 155, 157, 162, 260 and 462**; all remain COMPLETE. Two further FAILED-claim cases (case_178, case_547) rest on omission from **declared**-scope snapshots, so they are not flagged; that is reported for a decision. The 12 contested ownership flags among the 33 are unchanged. The review queue went from 106 to 111 (case_155 was already queued). `output.csv` is unchanged (`1d9870ad…cfde6`; _note: current submitted `output.csv`: `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37`, after the `retained_order_loaded` parser fix added one step to case_220_).

**Extension (2026-10-25):**
- The failed-claim conflict now also covers omission from declared-scope snapshots. That adds exactly case_178 and case_547, for 8 in total, all still COMPLETE.
- An account-attribution review is added when a contested account carrying such a conflict is also a tie rival of another case. Only case_547 qualifies: `account_410` is a rival in case_23's tie. The account is not reassigned.
- The review queue is now 112. `output.csv` is unchanged (`1d9870ad…cfde6`; _note: current submitted `output.csv`: `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37`, after the `retained_order_loaded` parser fix added one step to case_220_).

## 10. Independent verifier and parser-coverage test (2026-10-25)

`code/evaluation/verify_output.py` turns the independent evaluator's checks (`docs/reviews/evaluation-2026-10-25.md`) into a checked-in, read-only tool. It uses only the standard library, never imports `code/audit/*`, and reads the raw `dataset/` files plus the shipped extraction caches.

- **Hard failures (exit 1):**
  - the CSV contract: rows, header, sort, statuses, JSON, keys, numbering, phase/operation/state, order, evidence required or forbidden
  - every citation exists, is captured at or before `audit_at`, and covers its resource (directly, by absence-by-omission from a snapshot of that system, or by a reference link)
  - every finding's resource is tied to the requester
  - COMPLETE contains only cited verifications
  - retained records are never deleted
- **Warnings:** the cited file's wording for the claimed state, and policy by record type. Policy is judged only on explicit category labels; weak hints (`attachment_pii_scan` / `message_pii_scan`) can only reveal a conflict.
- **Blind spots fixed:**
  - SQL booleans stored as `'1'` / `'0'`
  - support attachment vs message detection
  - declared snapshot scopes read from the raw file

| Input | Rows | Citations | Findings | FAIL | WARN |
|---|---|---|---|---|---|
| Submitted `output.csv` (`bf634e2c…0e37`) | 518 | 1,109 | 722 | **0** | 1: case_34 `support_9538` is labelled `SUPPORT_MESSAGE` by the account-admin screenshot but scanned as an attachment PDF in the logs; the output deletes it |
| Gold `dataset/sample_output.csv` | 32 | 75 | 41 | 0 | 0 |
| Agent output on the samples | 32 | 68 | 41 | 0 | 0 |

**Parser-coverage regression test** (`code/tests/test_parser_coverage_and_verifier.py`): every one of the 1,071 non-start log lines that carry a `resource_id` must yield an evidence card. The only documented exception is the preview-service `thumbnail_failed` line. As a check, reverting the `retained_order_loaded` fix in a temporary copy makes this test fail and name that exact line.

## 11. Proposed cases P1–P8 adopted (`code/tests/test_proposed_cases.py`)

All 8 cases from `docs/reviews/evaluation-2026-10-25.md` §4 are now regression tests:
- **P1:** historical email with capitals and spaces; hash-only analytics link
- **P2:** evidence exactly at `audit_at` counts; a file captured 1 s later does not
- **P3:** same-name decoy with a different user_id
- **P4:** a CLASSIFY_REQUEST activity contradicting a German deletion text
- **P5:** marketing-only opt-out in other languages
- **P6:** a single OCR misread repairs only to a known identifier
- **P7:** a `retained_order_loaded` trace yields a cited legal-hold check
- **P8:** a reading older than the 14-day horizon is not proof

7 passed on the existing code. **P5 exposed a real intent bug:** "Merci de me supprimer uniquement de la liste marketing" was classified as a **deletion**, and the Spanish and Portuguese variants as undetermined.
- **Fix:** `audit/intent.py` now recognises "only … marketing" in ES/PT/FR/DE/IT as a non-deletion request, unless the phrase is negated ("pas seulement …", which stays a deletion).
- **Effect:** no change to any output. The dataset's only marketing requests are English. The agent output is still `bf634e2c…0e37`, the engine output `1bbba042…b095`, the samples 1.000 / 0.971 / 0.688, and the text rules still find 10 eval and 0 sample non-deletions.

## 12. Efficiency (2026-10-25, measured)

The full write-up is in `docs/reviews/architecture-efficiency-2026-10-25.md`. All timings are from this machine and were written to temporary outputs only.

| Stage | Time |
|---|---|
| Evidence parse (cold) / card cache load (warm) | 0.24 s / 0.06 s |
| Global workflow attribution, 550 cases | 0.068 s (about linear: 1,100 cases take 0.121 s) |
| Engine per-case loop, 518 cases | 0.115 s (about 0.22 ms per case) |
| Agent loop + gates G1–G11, 518 cases | 0.80 s |
| End-to-end `python code/agent_main.py --no-llm` | about 1.5 s |
| Independent verifier, 518 cases | 0.35 s |
| Unit tests, 187 | 9.5 s |

- **Hotspot:** `validate.py:15` rebuilds the activity-time lookup over 4,011 rows on every call. That is 1,036 calls and about 30% of agent-loop time.
- **Threads:** 4 threads were *slower* than sequential (0.154 s vs 0.115 s), with identical output.
- **Recommendation:** no change to the architecture. Optional behavior-neutral speed-ups are listed in the review.
- **Cost and determinism:** 0 model calls and $0. Two runs are byte-identical: `bf634e2c…0e37`, the same as the submitted output.

**Update (§12):** speed-up step 1 was adopted through the sandbox workflow (`docs/reviews/recovery-2026-10-25.md`). `validate_rows` now builds the activity lookup once. The agent run went from 1.5 s to 1.0–1.1 s, with output byte-identical (`bf634e2c…0e37`). 192 tests.

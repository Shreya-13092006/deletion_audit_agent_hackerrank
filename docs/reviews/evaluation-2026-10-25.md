# Independent Evaluation, 2026-10-25

Scope: all 32 public samples (agent output, `python code/agent_main.py --no-llm --split sample`) and a seeded random 40 of the 518 eval cases (`random.seed(20261025)`), drawn from the submitted root `output.csv`. The contract and citation checks cover all 518 cases.

Method: throwaway standard-library scripts read the raw `dataset/` files, plus the shipped extraction caches `code/cache/image_facts.json` and `pdf_text.json` as data. They never import `code/audit/*`.

Submitted `output.csv` sha256: `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37`.

## 1. Baseline (actual runs)

| Command | Result |
|---|---|
| `python -m unittest discover -s code/tests -t code/tests` | **170 tests OK** |
| `python code/evaluation/main.py -v` (engine on the samples) | status 1.000 · step P/R/F1 0.995 / 0.948 / 0.971 · evidence 1.000 · sequence 0.688 (22/32) · failing: case_03, 04, 18, 20, 21, 23, 25, 26, 27, 28 |
| `python code/evaluation/main.py --custom` | 6/6 |
| `python code/main.py --out <tmp>` (written to temp, so the submitted file was not overwritten) | 518 rows, 0 validation problems, sha256 `1bbba042…b095` |
| Agent on the samples | byte-identical to the engine on all 32 |

## 2. Per-check pass rates

| Check | 32 samples | Seeded 40 eval | All 518 |
|---|---|---|---|
| 1. Identity: each step's resource tied to the requester by an identifier, resource link, repopulation or workflow window | 102/102 | 147/147 | 722/722 findings |
| 2. Citations: the cited file exists, covers the resource and supports the claimed state | 68/68 after review (1 checker false positive) | 92/92 after review (4 checker false positives) | 1,109 resolve to real evidence; 51 are absence-by-omission or reference links, all validated |
| 3. Timestamps: nothing cited after `audit_at` | 68/68 | 92/92 | 1,109/1,109 |
| 4. States and policy (`deletion_rules.csv`) | 102/102 after review (4 checker false positives) | 147/147 after review (2 checker false positives) | n/a |
| 5. Ordering and contract | pass | pass | 518 unique rows, numeric sort, valid JSON, consecutive step numbers, correct phase/operation/state, future evidence `""`, NOT_APPLICABLE = `[]` |
| 6. Status: COMPLETE needs cited proof, plus a search for missed records | 10/10 COMPLETE proven; 0 false negatives (case_17's 2 omitted records are also omitted by gold) | 7/7; 0 false negatives | n/a |
| Parser coverage: every non-start log line with a `resource_id` has an evidence card | n/a | n/a | 1,071/1,072; the 1 exception is `thumbnail_failed`, preview-service noise |

**Checker false positives, verified against the raw data and the gold:**
- SQL inventories store `enabled` and `restore_allowed` as `'1'` (5 citations).
- `support_*` records that are subject-only attachments are correctly DELETE (`attachment_pii_scan` evidence). In the samples the gold agrees: case_07, 10 and 13.
- `analytics_9914` (case_12) is the documented contact/opt-in exception, and the gold agrees.

## 3. Findings

No critical or major findings.

| Case | Check | Observed | Expected | Evidence | Severity |
|---|---|---|---|---|---|
| case_04 | step | 1 of 2 gold steps | + VERIFY_ABSENT `account_004` [evidence_54] | the ID appears only in `sample_output.csv` | minor: not discoverable |
| case_18 / case_20 | step | missing VERIFY_PRESENT `audit_record_6645` / `_5569` [""] | gold | the IDs appear only in `sample_output.csv` | minor: not discoverable |
| case_03, 21, 25, 26, 27, 28 | step | missing VERIFY_ANONYMIZED on 1 analytics record each | gold | identity-less record whose workflow window is shared by 2–6 cases; no ownership feature found (timing, metrics, revenue, products, cohort) | minor: tie |
| case_23 | step | VERIFY_ABSENT `account_9155` | `account_410` | 4 NOT_STARTED cases compete for 3 FAILED deletes; each account appears only in its own activity row; flagged `ACCOUNT_WORKFLOW_TIME_ONLY_TIE` | minor: contested tie, already flagged |
| docs | docs | README says "# 139 tests"; `evaluation_report.md` header says "59 tests" and names `python code/main.py` and `7a9683fd…` as producing the final output | 170 tests; submission produced by `agent_main.py` (`bf634e2c…`) | `README.md:39`, `evaluation_report.md:1-10` | minor |
| packaging | release | no `code.zip` yet | required deliverable | repo root | minor; checked by `/integration-release` |

**False positives** (wrong COMPLETE, or unsupported claims): none found.

**False negatives** (a remaining record or active path the output omits): none found among identifier-tied records. The 10 sample gaps are records that can't be discovered or attributed.

**Unsupported conclusions** (accepted but weak, already flagged for review):
- 64 time-only account ties: 20 are COMPLETE and 12 rest on omission-only proof.
- 33 COMPLETE cases rest on omission from replica snapshots whose scope is not declared; all meet the 4-condition policy.
- 8 FAILED-claim-versus-omission conflicts.
- 15 proof-gate downgrades that cannot be scored.

## 4. Proposed new cases (proposal only; not added to the suite)

Each case uses fictional data. The expected output is derived by hand from the rules.

| # | Kind | Input | Expected | Reasoning |
|---|---|---|---|---|
| P1 | edge | request email `"  R.Vale.OLD@Example.TEST "` (historical, caps, spaces); `analytics_201` keyed only by `sha256("r.vale.old@example.test")`; account 404 at audit | INCOMPLETE: REPORT_EXPOSED_PII analytics_201 → ANONYMIZE → VERIFY_ANONYMIZED; VERIFY_ABSENT account | trim and lowercase; historical identity; hash link (AGENTS §6.5) |
| P2 | edge | the only reading of `search_202` is in a snapshot captured **exactly** at `audit_at`; a second snapshot captured `audit_at + 1s` shows it absent | INCOMPLETE, citing the at-cutoff file | "at or before `audit_at`" is inclusive; later evidence must not change the answer |
| P3 | adversarial | a search row with the same display name as the requester but `customer_reference=user_999` | not linked; no step | never link on names; a record naming another user is a decoy |
| P4 | adversarial | `CLASSIFY_REQUEST "non-deletion"` activity, while the request text says "Bitte löschen Sie mein Konto" | deletion authorized, flagged `INTENT_CONFLICT` | the text authorizes deletion; the activity is a claim |
| P5 | adversarial | "Por favor, elimínenme solo de las listas de marketing" | NOT_APPLICABLE, `[]` | marketing opt-out only, in Spanish (the "remove" trap in another language) |
| P6 | adversarial | OCR reads `backup_92B7`, which is unknown and one digit away from known `backup_9287` | repaired to `backup_9287` only if 2 of 3 readings agree; otherwise dropped | closed-world OCR repair |
| P7 | regression (parser fix) | pipe log: `retained_order_query_started subject_ref="user_900"` then `retained_order_loaded resource_id="legal_hold_90"` | VERIFY_RECORD_PRESENT legal_hold_90 | covers the `retained_order_loaded` omission found today |
| P8 | regression (§4 freshness) | the only reading is 20 days before `audit_at` | no cited COMPLETE; future check only | 14-day freshness horizon |

## 5. Recommended improvements (ranked)

1. **Fix the stale documentation** (minor, safe): test count in README; the header of `evaluation_report.md` (test count, producing command, hash).
2. **Turn this evaluator's independent checks into a checked-in, read-only verifier** under `code/evaluation/` with the two checker blind spots fixed (SQL `'1'` booleans; attachment detection), so `/test_` and release gates use them every run.
3. **Add a parser-coverage regression test:** every non-start log line with a `resource_id` must yield an evidence card, except an explicit noise list. This would have caught `retained_order_loaded` automatically.
4. **Add P1–P8 as custom or regression cases.** P2, P5 and P7 cover behavior not yet pinned down by tests.
5. **Build `code.zip` and run `/integration-release`.** Packaging and the release gate are not done yet.
6. **Leave the 10 sample gaps alone.** No evidence-backed fix exists; forcing them would mean inventing IDs or guessing between people.
7. *Optional, billable, needs approval:* re-run the stale Gemini planner evaluation.

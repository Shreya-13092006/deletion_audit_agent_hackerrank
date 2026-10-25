---
name: test_
description: Full-coverage test of the deletion-audit output - check every one of the 518 evaluation cases (plus the 32 public samples) against the output contract, recompute each case's identity and entity links from the raw dataset files, verify every citation and its audit_at cutoff, verify every COMPLETE has proof for every linked record, compare engine vs agent output, and report every case that fails. Read-only by default; it produces a candidate output.csv only into a separate file and never overwrites the root output.csv without explicit approval. Use when the user runs /test_, asks to "test all cases", or wants to know whether output.csv is linked and supported correctly for every case.
argument-hint: "[path to a candidate output.csv] [case ids to focus on] (optional; default: root output.csv, all cases)"
---

# /test_ - check every case, trust nothing

The goal is an `output.csv` in which **every case is checked** and every entity is linked to the right person by evidence. There is **no gold for the 518 evaluation cases**, so this skill can prove an output *consistent and supported*, not *correct*. Never claim 518/518 accuracy. The only accuracy numbers are on the 32 public samples.

Note: `dataset/deletion_requests.csv` has **518** rows. If someone says "519", count the rows and say so.

## Hard rules

- **Read-only by default.** Don't edit product code, tests, expected answers, `dataset/`, or the root `output.csv`.
  - Write candidates only to the scratchpad or job temp directory, e.g. `python code/agent_main.py --no-llm --out <tmp>/candidate.csv --cards-out <tmp>/cards.json`. A plain `python code/agent_main.py` or `python code/main.py` overwrites the root `output.csv`.
  - Adopt a candidate only after the user explicitly approves, and keep the old file and its SHA-256 for comparison.
- **Independent recomputation.** The checks in §2–§5 use your own throwaway scripts: standard library only, run with `python -I`, reading raw `dataset/` files. Don't import `code/audit/*`, because shared code shares bugs. You may read the shipped extraction caches `code/cache/image_facts.json` (screenshots) and `code/cache/pdf_text.json` (PDFs) as data.
- **No model calls, no installs, no commits or pushes, no secrets.** Use `--no-llm` on every run.
- **Never invent records or identifiers.** A resource that appears in no participant-visible evidence is reported as "not discoverable", never added.
- **Failures are reported, not fixed here.** Route them to `/architecture-challenger <report>`, which uses the failure-recovery subagent and the change-validator.

## 1. Baseline (record actual output)

```
python -m unittest discover -s code/tests -t code/tests
python code/evaluation/main.py -v                  # 32 samples vs dataset/sample_output.csv
python code/evaluation/main.py --custom
python code/evaluation/agent_eval.py --no-write   # engine vs agent, tune/hold-out split
python code/main.py --no-llm --out <tmp>/engine.csv
python code/agent_main.py --no-llm --out <tmp>/agent1.csv --cards-out <tmp>/cards1.json
python code/agent_main.py --no-llm --out <tmp>/agent2.csv --cards-out <tmp>/cards2.json
```

Record:
- SHA-256 of the root `output.csv`, `engine.csv`, `agent1.csv` and `agent2.csv`
- whether the two agent runs are byte-identical (determinism)
- which cases differ between engine and agent, and why (the `decision.source` and `flags` on each case card)

## 2. Contract, every row

Check the candidate against `dataset/deletion_requests.csv`:
- **Rows:**
  - exactly 518 data rows, with header `case_id,deletion_status,steps_json`
  - UTF-8, no BOM, 3 fields per row
  - no duplicate, missing or extra `case_id`
  - sorted by `case_id`, numerically: case_2 before case_10
- **Status:** `deletion_status` is COMPLETE, INCOMPLETE or NOT_APPLICABLE.
- **steps_json:** parses as a JSON array.
  - NOT_APPLICABLE means `[]`. COMPLETE or INCOMPLETE means non-empty.
  - Each step has exactly the 7 keys.
  - `step_no` runs 1..n.
  - phase, operation and state match the table in `AGENTS.md` §6.4.
  - Order is phase, then operation-table order, then `system_id`, then `resource_id`.
- **Evidence:**
  - FINDING steps, and every step of a COMPLETE case, cite evidence.
  - Remediation and post-fix verification steps in an INCOMPLETE case have `evidence_id == ""`.

## 2b. Two separate questions for every step

Answer and report these separately. Never merge them into one pass/fail.

1. **Ownership:** does independent evidence tie the resource to this requester? Report the tier from the case card (`step_audit[].ownership.tier`), then re-derive it yourself (§3):
   - `proven`: an exact identifier, or a resource link, in evidence at or before `audit_at`
   - `proven-later`: an identifier only in evidence captured after the cutoff
   - `inferred`: deletion-workflow attribution
   - `contested`: an attribution decided by time alone

   A tier describes the basis; it does **not** make a step invalid. Keep inferred verification steps. The only hard rule is G10: a FINDING needs `proven` ownership. A contested step stays flagged for review.
2. **State:** does the evidence establish the asserted state at `audit_at`? Classify each step:
   - `direct`: a reading of the record in the cited file
   - `omission`: the cited snapshot covers the system and omits the record
   - `future`: no evidence; a post-remediation check

   For `omission`, the scope must be **declared** (a `snapshot_scope` row or a bundle `data_store`) and inside the 14-day window. Flag an `inferred` scope (replica or failover files) or a `targeted` capture (few records) as not exhaustive. Report them; don't treat them as proof, and don't silently change the output.

**Evidence gaps** go on the case card (`evidence_gaps`) and in the report, never into `output.csv`:
- `primary_account_not_identified`
- `no_security_audit_record`
- `workflow_tie`
- `account_time_only_tie`
- `retained_record_unreadable`

**Misses on the samples:** classify every gold step the output lacks:
- **tie:** the record is shared by several cases, or is an account rival
- **not discoverable:** the ID appears in no participant file, activity row or extraction cache
- **parser/search error:** the ID is present in participant data but was not produced. Only these are real bugs.

`python code/evaluation/agent_eval.py --no-write` prints this table.

## 3. Identity and entity links, every case

For each case, rebuild the subject from `user_identities.csv` plus `user_audit_log.csv`:
- the email trimmed and lowercased, current or historical
- `user_id`
- every historical email and `email_hash`
- `sha256(lowercased email)` for every email

Then, for every `resource_id` in the case's steps, find the evidence that ties it to *this* subject:
- the same record or row carries one of the subject's identifiers, under any alias field (`customer_reference`, `subject_reference`, `subject_selector`, `lookup_key`, `lookup_value`, `requester_email`, message text, and so on)
- or a log trace: the `*_started` line carries the identifier and the `*_completed` line carries the resource, joined by `trace_id`
- or a resource link: a search document's `source_resource_id`, or a `LINK_RESOURCE_IDENTITY` activity row, including a business reference such as a statement number
- or a recreation path: an activity row saying a connector or backup repopulated a linked resource
- or a documented workflow attribution, which the case card flags as `ACCOUNT_FROM_WORKFLOW_ACTIVITY`

Flag these:
- **name-only links:** never valid
- **links through an identifier belonging to another `user_id`:** a decoy
- **phone-only links:** phones are provenance, never a link key
- **ties decided only by time:** `ACCOUNT_WORKFLOW_TIME_ONLY_TIE`, reported as a risk

Also look for **missed entities**:
- grep every evidence file captured at or before `audit_at`, and in the 14-day freshness window, for the subject's identifiers
- list resources tied to the subject that the output omits

Each one is a possible false negative. Classify it before reporting: out of policy, already compliant, or a real omission.

## 4. Citations and the time cutoff, every cited step

For each `evidence_id`:
- it resolves in `evidence_files.csv` (file), `system_activity.csv` (activity) or `user_audit_log.csv` (audit)
- its `captured_at` or `event_time` is at or before the case's `audit_at`
- it shows the claimed state at a time within 14 days before `audit_at`:
  - REMAINING or PRESENT means the record is there
  - ABSENT means not found, a 404, or absence by omission
  - REDACTED or ANONYMIZED means identifiers are removed or null
  - DISABLED or BLOCKED means `enabled=false` or `restore_allowed=false`
  - EXPOSED_PII means identifiers are still visible
- no later reading at or before `audit_at`, in any file, contradicts it
- within one snapshot, any copy present means present

A resource missing from the cited file is valid **only** as absence by omission:
- the file is a snapshot whose scope (`snapshot_scope`, `data_store`, primary or replica tables) covers that system
- no file in the window mentions the resource

The public gold uses this pattern, e.g. case_01 cites `evidence_54` for a missing account. Anything else is a fabricated citation.

## 5. Status, every case

- **COMPLETE:** every linked record, flow and backup, plus the subject's primary account, has a cited compliant reading at or before `audit_at`.
  - A COMPLETE resting on a workflow claim, a stale reading or only post-cutoff evidence is a **false positive**.
  - Exception: when no account is tied to the subject in *any* participant file, report it as a minor missing step, not a wrong status. Gold case_04 is COMPLETE in exactly that situation.
- **INCOMPLETE:** each finding has evidence of the violation. The remediation covers each violating record, flows are disabled and restores blocked before records are changed, and verification covers each remediated or retained record.
- **NOT_APPLICABLE:** the request text does not ask for deletion (access, copy, correction, login help, invoice, marketing opt-out only).
  - Check all 10 by reading the text.
  - Also check that no deletion request was marked NOT_APPLICABLE.
- **Policy:** each step matches `deletion_rules.csv` for its record type.
  - retained security or legal records: VERIFY_PRESENT, never deleted
  - tombstones: REDACT, keeping only the user reference
  - analytics or telemetry: ANONYMIZE
  - support messages and email-delivery logs: REDACT
  - everything else listed: DELETE
  - backups: BLOCK_RESTORE
  - active flows: DISABLE

## 6. Report

Write the findings in your reply. Write a file only if the user asks; if they do, use `docs/reviews/test-all-YYYY-MM-DD.md`.

Include:
- the baseline numbers and the SHA-256 values
- a per-check pass count over **all** cases (not a sample)
- a findings table: case, check, observed, expected, evidence, and a severity of critical, major or minor
  - **critical:** a wrong COMPLETE, a fabricated citation, a citation after `audit_at`, or a contract break
  - **major:** a wrong or missing record or state, or a decoy link
  - **minor:** ordering, a missing optional verification, or an account that isn't discoverable
- false positives, false negatives and unsupported conclusions, listed separately
- the engine vs agent differences, each with its evidence
- **GO / NO-GO** for adopting the candidate as the root `output.csv`. Also check that the documented run command (`README.md`, `code/evaluation/usage_report.md`) reproduces the candidate's SHA-256.

Append the `log.txt` turn entry required by `AGENTS.md`.

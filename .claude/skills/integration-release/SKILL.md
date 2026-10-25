---
name: integration-release
description: Final gate for the deletion-audit submission - reconcile conflicting recommendations from architecture, evaluation and recovery reviews, run the full test suite and the complete 518-case pipeline, verify output.csv, code.zip, evaluation report, usage report and log.txt transcript, compare against the original baseline, and block release when any deliverable or correctness check fails. Use last in the review chain, when the user runs /integration-release, or asks whether the solution is ready to submit.
argument-hint: "[baseline reference, e.g. a review file or an output.csv sha256] (optional)"
---

# /integration-release — combine approved changes and decide go / no-go

Step 3 of 3 in the review chain:
1. `/architecture-challenger` (delegates fixes to `failure-recovery`; validated by `change-validator`)
2. `/independent-evaluator`
3. `/integration-release`

**This skill decides; it does not invent fixes.** Missing work goes back to the right skill.

## 1. Reconcile recommendations

Read the latest files in `docs/reviews/`: `architecture-*` (including its failure-recovery subagent results), `recovery-*` and `evaluation-*`.

**Check every adoption recorded in `recovery-*.md`.** Each one needs two things:
- a `change-validator` verdict of APPROVE covering exactly the adopted files
- a recorded user approval

An adoption missing either is a **blocking** item. List every recommendation together with its status: applied, pending or rejected.

**When recommendations conflict:**
1. Correctness and safety rules come first: `AGENTS.md` §6, no fabrication, the audit cutoffs, determinism.
2. Then measured accuracy.
3. Then simplicity.
4. Then latency and cost.

Record each decision and the reason for it. Recommendations the user hasn't approved stay pending; don't apply them here.

## 2. Full verification (run everything, quote actual output)

```
python -m unittest discover -s code/tests -t code/tests
python code/evaluation/main.py
python code/evaluation/main.py --custom
python code/main.py
python code/main.py          # second run: the sha256 must match the first
```

## 3. Release checklist (each item is PASS or FAIL, with evidence)

**`output.csv` at the repo root:**
- exact header `case_id,deletion_status,steps_json`
- 518 rows, one per `dataset/deletion_requests.csv` case_id, sorted by case number
- statuses only COMPLETE, INCOMPLETE or NOT_APPLICABLE
- every `steps_json` is a valid JSON array with consecutive `step_no` and only allowed phase, operation and state combinations
- the ordering contract holds
- NOT_APPLICABLE means `[]`
- findings and COMPLETE verifications cite an existing `evidence_id` captured at or before `audit_at`
- remediation and post-fix verification steps use `""`
- no INCOMPLETE case has empty steps without a recorded flag

**Tests and evaluation:**
- every test passes
- every custom case passes
- sample metrics are at least the baseline

**Reports:**
- `code/evaluation/evaluation_report.md` contains status, step, field and sequence accuracy, at least 3 custom cases, failures found and improvements made. Its numbers must match this run exactly.
- `code/evaluation/usage_report.md` describes this run: providers and models, calls, input and output tokens, total and average per request, estimated total and per-request cost.

**`code.zip`:**
1. Build it from the repo root with the README command (Windows: `Compress-Archive -Path README.md, code -DestinationPath code.zip -Force`), after removing `code/**/__pycache__`.
2. Inspect the listing. It must include `README.md`, `code/main.py`, `code/audit/`, `code/evaluation/*.md` and `code/requirements.txt`.
3. It must exclude `dataset/`, virtual environments, `__pycache__`, nested archives (`.zip`, `.tar`, `.gz`, `.7z`, `.rar`), `.env` and any API keys.
4. Grep the archive contents for `sk-ant`, `api_key=` and `ANTHROPIC_API_KEY=`; there must be no secrets.

**README:** setup and run commands work exactly as written.

**`log.txt` (chat_transcript):**
- entries follow `AGENTS.md` §5
- every entry has exactly one non-empty `tool=` and one non-empty `model=` line
- no secrets

**Repository hygiene:** nothing under `dataset/` changed (`git status --short dataset/` is empty).

## 4. Compare against the original baseline

The baseline is the earliest numbers in `code/evaluation/evaluation_report.md`, or the one the user names. Build a table: metric, baseline, now, delta.
- Explain every regression.
- Diff the eval `output.csv` against the baseline copy if one exists, and summarize the changed rows by cause.

## 5. Decision

- **BLOCK** if any checklist item fails, any critical finding from the reviews is open, the reports disagree with the measured numbers, or the output is nondeterministic. List the blocking items and the skill that should handle each one. Fix work goes to `/architecture-challenger`, which delegates it to the `failure-recovery` subagent.
- **GO** only when everything passes. Then give the user:
  - the deliverables: `code.zip`, `output.csv`, `log.txt` as chat_transcript
  - the submission link: https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
  - the remaining known limitations

Never commit or submit on the user's behalf unless they ask.

Write `docs/reviews/release-YYYY-MM-DD.md` with the reconciliation, the checklist, the baseline comparison and the decision. Then append the `log.txt` turn entry required by `AGENTS.md`.

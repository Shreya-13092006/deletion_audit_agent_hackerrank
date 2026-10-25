# Session Summary — Ghost Data Still Exists (2026-10-25)

Tool: Claude Code · Model: claude-opus-5-5 · Branch: `solution-baseline`. Nothing was committed or pushed, and no API calls or installs were made.

## Current state

| Item | Value |
|---|---|
| Submitted `output.csv` | sha256 `bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37`: 370 INCOMPLETE, 138 COMPLETE, 10 NOT_APPLICABLE |
| Produced by | `python code/agent_main.py --no-llm` (proof-gated agent) |
| Baseline engine | `python code/main.py`, sha256 `1bbba042…b095` |
| Original baseline backup | `docs/reviews/recovery-artifacts/20261025-verification/backup/output.csv`, sha256 `7a9683fd…ea50` |
| Unit tests | **183, all passing** |
| Sample accuracy (32 public cases) | status 1.000 · step F1 0.971 · evidence 1.000 · sequence 0.688 (22/32 exact) |
| Hold-out (8 cases) | status 1.000 · step F1 0.965 · sequence 0.625 |
| Independent verifier | submitted output: 0 FAIL, 1 WARN; gold samples: 0 FAIL, 0 WARN |
| Model usage | 0 calls, $0.00 |

Accuracy on the 518 eval cases can't be measured, because their correct answers aren't published.

## What was done, in order

1. **Proof gates (G3/G9) and a fail-safe.** Every citation must show the claimed state, be no more than 14 days old and not be superseded by a later reading. A COMPLETE answer must account for every linked record and the person's main account. A COMPLETE without proof becomes INCOMPLETE and is flagged. Result: 15 cases changed from COMPLETE to INCOMPLETE; no sample changed.
2. **Corroboration tool.** A real `unresolved` outcome exists now, and unverified "succeeded" claims are recorded. A no-progress stop was added to the agent loop.
3. **Tests for policy gaps.** The 5 record types that had no tests are now covered. Phone numbers never link records on their own, and conflicting readings are kept as separate entries.
4. **Adopted the proof-gated output** after a read-only review, and documented both commands in the README and the usage report.
5. **Ownership checked separately from state.** Every step now records how ownership was established (proven / proven-later / inferred / contested) and what proves its state (direct / omission / future). New check **G10**: a finding must have proven ownership; there are 0 failures across 722 findings.
6. **Snapshot-omission policy (flag-only).** Absence inferred from a record missing in a snapshot counts only if 4 conditions hold. Snapshots that hold only one system are accepted, which matches the gold's use of `evidence_54`. Eight cases where a failed delete claim conflicts with omission-only proof are flagged for review (58, 155, 157, 162, 178, 260, 462, 547). case_547's account attribution is also flagged, because of the case_23 / `account_410` tie.
7. **Investigation of the 10 imperfect samples.**
   - 3 are **not discoverable**: `account_004`, `audit_record_6645` and `audit_record_5569` appear only in the gold file.
   - 7 are **ties** between people with equal evidence.
   - None can be fixed without inventing IDs or guessing ownership.
8. **Parser fix.** The `retained_order_loaded` log event (`legal_hold_4961`, user_218) was being ignored. Fixing it adds one step to case_220. This is the change that produced the current output hash.
9. **Independent evaluation** (`docs/reviews/evaluation-2026-10-25.md`): no critical or major findings, no false positives and no false negatives.
10. **Items 1–3 from that review:**
    - fixed stale documentation
    - added the independent verifier `code/evaluation/verify_output.py` (standard library only)
    - added a parser-coverage regression test (1,071 of 1,072 log lines covered; the one miss is preview-service noise). A mutation check confirmed the test catches the original bug.
11. **Proposed cases P1–P8 adopted as tests.** P5 exposed a real bug: French "supprimer uniquement de la liste marketing" ("remove me only from the marketing list") was classified as a deletion. It is fixed with a negation-guarded multilingual "only … marketing" rule, with no output change.

## Open items and known limits

- **10 sample gaps:** 3 not discoverable and 7 ties. These are data limits, not bugs.
- **Review flags (no output change):**
  - 64 accounts attributed by timing alone (20 of them COMPLETE)
  - 33 COMPLETE answers resting on omission from replica snapshots
  - 8 failed-claim conflicts
  - 15 downgrades that can't be scored
  - case_34: the category of `support_9538` is in conflict (screenshot says message, log says attachment)
- **Not done yet:** build `code.zip` and run `/integration-release`.
- **Interrupted:** the architecture efficiency measurement (stage timings, scaling, parallel experiment) was stopped by the user before it ran.
- **Stale and billable:** the Gemini planner evaluation is out of date, and re-running it needs approval.
- **Pending from earlier:** cleaning the exposed Gemini key out of transcripts and logs was never done.

## Key files

- Code:
  - `code/audit/agent/` (gates.py, ownership.py, tools.py, loop.py, state.py)
  - `code/audit/parsers/logs.py`
  - `code/audit/intent.py`
- Evaluation:
  - `code/evaluation/verify_output.py`, `agent_eval.py`
  - `evaluation_report.md` §8–§11, `usage_report.md`
- Tests:
  - `code/tests/test_agent_proof.py`, `test_agent_ownership.py`
  - `test_parser_coverage_and_verifier.py`, `test_proposed_cases.py`
- Reviews:
  - `docs/reviews/evaluation-2026-10-25.md`
  - `docs/reviews/recovery-artifacts/20261025-verification/` (backup, changed_cases.md, candidate outputs)
- Skill: `.claude/skills/test_/SKILL.md`, a full-coverage read-only test of all cases.
- Transcript: `log.txt`, one entry per turn.

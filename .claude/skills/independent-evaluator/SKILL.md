---
name: independent-evaluator
description: Skeptical, independent evaluation of the deletion-audit agent - recompute expected results from raw dataset files without trusting the pipeline's code, test identity matching, evidence citations, timestamps, deletion states and step ordering, generate edge, adversarial and regression cases, and report false positives, false negatives and unsupported conclusions. Never edits expected answers to make tests pass. Use second in the review chain, when the user runs /independent-evaluator, or asks whether the outputs can be trusted.
argument-hint: "[case ids or area to focus on, e.g. 'case_23 case_55' or 'citations'] (optional)"
---

# /independent-evaluator — trust nothing, recompute everything

Step 2 of 3 in the review chain:
1. `/architecture-challenger` (delegates fixes to `failure-recovery`; validated by `change-validator`)
2. `/independent-evaluator`
3. `/integration-release`

**Your stance is adversarial.** You are not a code reviewer agreeing with the implementation. Assume `output.csv` is wrong until you have checked it yourself.

## Hard rules

- **Never modify expected answers.** That covers `dataset/sample_output.csv`, the custom-case `expected` values and test assertions. If an expectation looks wrong, report it with evidence; don't change it.
- **Never modify anything under `dataset/`.**
- **Never fix product code in this skill.** Failures go to the `failure-recovery` subagent, through `/architecture-challenger docs/reviews/evaluation-YYYY-MM-DD.md`.
- **Recompute with your own throwaway scripts** in the scratchpad or temp directory, reading raw `dataset/` files with the standard library. Never import `code/audit/*` for the recomputation: shared code shares bugs.
- **Use only participant-facing data.** Never cite organizer-only data.

## 1. Baseline

Run these and record the actual results:
```
python -m unittest discover -s code/tests -t code/tests
python code/evaluation/main.py -v
python code/evaluation/main.py --custom
python code/main.py
```

## 2. Independent checks (sample all 32 sample cases plus a seeded random 40 eval cases)

For each check, count passes and list every failure with case_id, step and evidence.

1. **Identity:** recompute the subject from `user_identities.csv` plus `user_audit_log.csv`: lowercased emails, sha256 hashes and historical values. Verify that every resource in the case's steps is tied to that subject by an identifier, a resource link or a documented workflow attribution. Flag any link that rests only on a name, or on an identifier that belongs to another person.
2. **Citations:** every cited `evidence_id` must:
   - exist in `evidence_files.csv` or `system_activity.csv`
   - be captured at or before `audit_at`
   - actually contain the resource (grep the file, or the OCR cache for PNGs)
   - support the claimed state (PRESENT, ABSENT, ACTIVE and so on)
3. **Timestamps:** no fact dated after `audit_at` may change state. Re-derive each cited resource's state at `audit_at` by hand from the raw lines and rows.
4. **States and policy:** check each step's operation against `deletion_rules.csv` for its record type:
   - retained records are never deleted
   - tombstones keep only the user reference
   - analytics are anonymized, not deleted, unless the evidence shows a contact or opt-in record
5. **Ordering and contract:**
   - phase order, then operation-table order, then system_id, then resource_id
   - consecutive `step_no`
   - remediation and post-fix verification evidence is `""`
   - NOT_APPLICABLE means `[]`
   - 518 rows, sorted
6. **Status:** a COMPLETE case needs cited proof for every relevant record. Any COMPLETE whose proof you can't reproduce is a **false positive**. Any remaining record, active flow or open restore that the evidence shows but the output omits is a **false negative**.

## 3. Generate cases

Add at least 5 new cases to a *proposal* file. Don't add them to the suite yourself. Include:

- **Edge:**
  - an email with a trailing space and capitals
  - two historical emails
  - a hash-only link
  - evidence exactly at `audit_at`
  - a snapshot captured one second after `audit_at`
- **Adversarial:**
  - a decoy with the same name but a different user_id
  - a row showing another person's email
  - a CLASSIFY_REQUEST that contradicts the request text
  - an OCR digit confusion that would map to an unknown resource
  - a "remove from marketing only" variant in another language
- **Regression:** one per past bug listed in `code/evaluation/evaluation_report.md` §3–4.

Give each case its input, its hand-derived expected output, and the reasoning that cites dataset rules.

## 4. Report

Write `docs/reviews/evaluation-YYYY-MM-DD.md` with:
- the baseline numbers
- a per-check pass rate
- a table of findings: case, check, observed, expected, evidence, and a severity of critical, major or minor
- false positives, false negatives and unsupported conclusions, each listed separately
- the proposed new cases

**Severity:**
- **Critical:** a wrong COMPLETE, a fabricated citation, a citation after `audit_at`, or a broken contract.
- **Major:** a wrong record or state.
- **Minor:** ordering, or a missing optional verification.

Then summarize for the user, tell the user to pass the critical and major findings to `/architecture-challenger <this report>`, which briefs the `failure-recovery` subagent, and append the `log.txt` turn entry required by `AGENTS.md`.

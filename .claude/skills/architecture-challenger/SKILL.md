---
name: architecture-challenger
description: Review the deletion-audit implementation and challenge its architecture before any code changes - find bottlenecks and missing components, compare deterministic, parallel-worker, specialized-agent and hybrid designs on accuracy, latency, cost and reliability, decide what runs in parallel versus sequentially, and produce a migration plan that preserves working behavior. Delegates reproduction, fixes and rollbacks to the failure-recovery subagent inside a temporary sandbox copy of the current (uncommitted) project, has every result independently checked by the read-only change-validator subagent, and adopts only validator-approved changes after explicit user approval. Use first in the review chain, when an evaluation report has findings to fix, when the user runs /architecture-challenger, or asks whether the pipeline design is right.
argument-hint: "[focus area, e.g. 'workflow attribution', or a docs/reviews/evaluation-*.md with findings to fix] (optional)"
---

# /architecture-challenger — challenge the design, delegate fixes to a subagent

Step 1 of 3 in the review chain:
1. `/architecture-challenger` (delegates fixes to `failure-recovery`; validated by `change-validator`)
2. `/independent-evaluator`
3. `/integration-release`

**This skill doesn't edit code itself.** In the main working tree it writes only its reports in `docs/reviews/` and its `log.txt` entry. Code changes happen in two ways only:
- inside a temporary sandbox copy (`.claude/sandboxes/<id>/work`), made from the *current* project state, committed or not (§6)
- when the user approves adopting changes that `change-validator` approved (§7–§8), via `recovery_sandbox.py apply`

Nothing under `dataset/` is ever changed.

**Architecture of this skill:**
```
/architecture-challenger (main context: analysis, decisions, user approval)
  │  §1-§5  read-only analysis -> failure list + migration plan
  ├─ §6  recovery_sandbox.py create  -> .claude/sandboxes/<id>/{base (read-only), work, manifest.json}
  │      brief ─► failure-recovery subagent (own context; edits and tests only in work/)
  │             reproduce -> isolate -> fix + regression test -> rerun -> keep or roll back -> diff
  │       ◄─ "Recovery result" + changes.patch + changed_files.json
  │      recovery_sandbox.py verify  (main project unchanged? base + dataset fixture intact?)
  ├─ §7  brief ─► change-validator subagent (read-only: no Edit/Write)
  │             verify -> own diff (git diff --no-index base work) -> checks -> re-measure in work -> re-check
  │       ◄─ "Validation verdict: APPROVE | REJECT"
  ├─ §8  APPROVE only -> ask the user -> recovery_sandbox.py apply --approved-by-user (drift check + backup)
  │      -> re-measure main project -> restore from backup if worse
  └─ §9  recovery_sandbox.py preserve -> confirm artifacts -> recovery_sandbox.py cleanup
```

Adoption order: **recovery → isolation verified → validation APPROVE → user approval → adoption.** Nothing is staged, committed or pushed.

## 1. Read before judging

Read these first:
- `AGENTS.md` (follow its logging rules)
- `problem_statement.md`
- `docs/master-prompt.md`
- `docs/dataset-observations.md`
- `code/evaluation/evaluation_report.md`
- the latest files in `docs/reviews/`

Then read the implementation:
- `code/main.py`
- `code/audit/pipeline.py`, `linker.py`, `state.py`, `policy.py`, `planner.py`
- `code/audit/parsers/`
- `code/audit/screen_ocr.py`
- `code/tools/extract_images.py`

**Measure the current baseline; never quote old numbers:**
```
python -m unittest discover -s code/tests -t code/tests
python code/evaluation/main.py            # sample split vs dataset/sample_output.csv
python code/evaluation/main.py --custom
python code/main.py                        # 518 cases; note runtime and the validation line
```
Record each stage's runtime. `python -X importtime` or a simple timer around `Auditor.__init__`, `assign_workflow_resources` and the per-case loop is enough.

## 2. Find bottlenecks and gaps

For each item, give the file and line, the evidence for it, and the cost of fixing it.

- **Accuracy bottlenecks:**
  - Which remaining sample failures are design limits, and which are bugs? Examples of design limits: workflow attribution ties, identity-less anonymized records, records that appear in no evidence.
  - Which eval flags (from `code/cache/audit_trail.jsonl`) are concentrated in one component?
- **Missing components:**
  - Is there a confidence score per step?
  - A second extraction backend for cross-checking?
  - A hold-out evaluation split?
  - A per-component regression baseline?
- **Latency and complexity:**
  - Repeated `link_resources` calls (it runs once per case and again inside attribution)
  - O(cases × activity) scans
  - Repeated OCR runs
- **Reliability:**
  - Windows-only OCR
  - Optional dependencies
  - Silent fallbacks
  - Nondeterminism (set ordering, file ordering, time)

## 3. Compare alternatives

Evaluate at least these four options on the same criteria:

| Option | Accuracy | Latency | Cost/run | Reliability/determinism | Effort | Risk to working behavior |
|---|---|---|---|---|---|---|
| Keep the deterministic sequential pipeline (current) | | | | | | |
| Parallel workers (parse files and audit cases concurrently) | | | | | | |
| Specialized LLM agents (intent, extraction, adjudication of ties) | | | | | | |
| Hybrid: deterministic core plus a model only for named ambiguous decisions | | | | | | |

**Rules for filling the table:**
- Base every cell on measured runtime, the current failure list and the token prices in `code/evaluation/usage_report.md`. Where no measurement exists, mark the cell as an estimate.
- A model must never decide state, identity or evidence citations on its own. Any model step must produce a validated structured output and stay subordinate to evidence (`AGENTS.md` §6.6).
- Prefer the simplest option that wins on accuracy. Concurrency for its own sake isn't a benefit: the full run is about 2 s.

## 4. Parallel versus sequential

Classify each stage:
- **Parallel-safe:** independent per file or per case, such as evidence parsing per file, or per-case auditing after global attribution.
- **Must stay sequential:** stages with global state or order dependence, such as identity graph loading, global workflow attribution (one-to-one matching), output sorting and validation.

State the determinism guard each parallel stage needs: a stable merge order, no shared mutable state, and an identical `output.csv` sha256.

## 5. Migration plan

Write small, reversible steps. Each step needs:
- the files it touches
- the expected metric change
- the tests to add
- a rollback trigger, e.g. sample step F1 falls below the baseline, sequence accuracy drops, or the `output.csv` hash changes unexpectedly

Working components stay untouched unless a step names them. Order the steps by score impact per unit of risk.

## 6. Delegate failures to the `failure-recovery` subagent

**When to delegate:** whenever the measured baseline or the input evaluation report shows any of these:
- failing tests or custom cases
- validation problems
- sample regressions compared with the previous report
- critical or major evaluation findings
- a migration-plan step that changes behavior

Design-limit items, where the data can't decide, are also sent, so the subagent can confirm and document them rather than guess.

**Isolation mode:** use a sandbox copy, made by `.claude/tools/recovery_sandbox.py`. It works with uncommitted and untracked files, so no commit, branch, stash or git worktree is needed. Don't use `isolation: "worktree"`: a worktree holds only committed files, and this project's solution may be uncommitted.

**Preflight.** Stop and report a BLOCKER to the user if any step fails:
1. Pick a sandbox id: `<YYYYMMDD>-<short-topic>`, using letters, digits, `.`, `_` and `-`.
2. Run `python .claude/tools/recovery_sandbox.py create --id <id>`. The tool stops (exit 2) when:
   - the solution code is missing
   - a possible secret is found
   - the sandbox already exists

   It copies `code/`, `dataset/` (as a read-only fixture), `README.md`, `AGENTS.md`, `CLAUDE.md` and `problem_statement.md`. It never copies `.git`, `.env`, `settings.local.json`, caches, `output.csv` or `log.txt`. It records the source state in `manifest.json`: git HEAD, branch, dirty files, and hashes of every copied file and every main-project file.
3. Run `python .claude/tools/recovery_sandbox.py verify --id <id>`. It must print `ISOLATION OK`.

**How to delegate:** use the Agent tool with `subagent_type: "failure-recovery"`, without `isolation`. Pass a failure brief:
- the sandbox id, plus the absolute paths of `SANDBOX`, `WORK` and `BASE`
- each failure: id, source, and observed versus expected behavior
- the baseline you measured: sample status accuracy, step F1 and sequence accuracy; test and custom-case counts; the eval `output.csv` sha256
- scope limits: the files that may change, and the components that must stay untouched

**After the subagent returns:**
1. Save its block to `$SANDBOX/reports/recovery-result.md` if it didn't.
2. Run `recovery_sandbox.py diff --id <id>`, so the diff reflects the final state.
3. Run `recovery_sandbox.py verify --id <id>`. **ISOLATION FAILED means stop:** report every listed main-project change to the user, don't validate or adopt anything, and don't clean up the sandbox, which is evidence.

**Parallel versus sequential:**
- **Default to one subagent in one sandbox, fixing failures one at a time.**
- Use parallel sandboxes only for failure groups whose bisected stages are disjoint, and adopt their results one after another.
- Before adopting a later result, recreate its sandbox if an earlier adoption touched the same files. `apply` refuses drifted files anyway.

## 7. Independent validation by the `change-validator` subagent

Don't judge the recovery result yourself; the approver must not check its own work.

**For every recovery result** with "Changes to adopt" or "Adopt: yes/partial", spawn the Agent tool with `subagent_type: "change-validator"`, without `isolation`. Pass a validation brief:
- the sandbox id and path
- the full "Recovery result" block
- your main-project baseline numbers
- the scope limits you gave the recovery subagent

Save the verdict it returns to `$SANDBOX/reports/validation-verdict.md`.

**Handling the verdict:**
- **REJECT:** don't offer the change. Record the blocking reasons. Either send the failure back to `failure-recovery` in the same sandbox, with the reasons appended (at most 2 retries per failure; rerun `diff` and `verify` after each), or record it as a limitation.
- **APPROVE:** go to §8. Only the files listed under "Files safe to adopt" are candidates, and they must appear in `changed_files.json`.

## 8. Your approval, then adoption

Adoption order: **recovery → isolation verified → validation APPROVE → user approval → adoption.** No shortcut exists.

1. Show the user the recovery result and the validation verdict side by side: per-failure outcome, before and after metrics as measured by the validator, and the files safe to adopt along with their hunks from `changes.patch`.
2. **Ask the user explicitly** (AskUserQuestion: adopt all, adopt some, or discard). No answer or an ambiguous answer means discard. Approval applies to this change only.
3. After approval, run:
   `python .claude/tools/recovery_sandbox.py apply --id <id> --approved-by-user --files <approved paths>`
   It refuses:
   - any file that changed in the main project since the sandbox was created (drift)
   - `dataset/` paths and generated artifacts
   - deletions, which are reported only

   It backs up each original to `docs/reviews/recovery-artifacts/<id>/backup/` and checks every copy against its hash.
4. Rerun the four measurement commands on the main project, plus a second `python code/main.py`, and confirm a stable sha256. The numbers must equal the validator's.
5. If the results are worse than the baseline or differ from the validator's, restore each adopted file from its backup (for new files, delete them only after confirming they were added by this adoption), and record it.
6. Don't stage or commit. Committing is a separate user decision.

Results marked "documented limitation" go into `code/evaluation/evaluation_report.md` §4, again with approval.

**Clean up only after the artifacts are preserved:**
1. Run `python .claude/tools/recovery_sandbox.py preserve --id <id>`. It copies the manifest, patch, changed-file list and reports to `docs/reviews/recovery-artifacts/<id>/` and checks every copy's hash.
2. Run `python .claude/tools/recovery_sandbox.py cleanup --id <id>`. It deletes only `.claude/sandboxes/<id>/`, and only after re-checking the preserved hashes. It never deletes main-project files.
3. Keep the sandbox (skip cleanup) whenever isolation failed or the user wants to inspect it.

## 9. Output

Write `docs/reviews/recovery-YYYY-MM-DD.md` with the sandbox id, the recovery result, the validation verdict, the isolation checks and the adoption decisions (the raw patch and manifest are in `docs/reviews/recovery-artifacts/<id>/`). Then write `docs/reviews/architecture-YYYY-MM-DD.md` with:
- the measured baseline
- the bottlenecks
- the comparison table
- the parallel/sequential map
- the recommendation, with the rejected alternatives and why
- the migration plan, with the steps already executed through the subagent marked

Give the user a 5-line summary, then append the `log.txt` turn entry required by `AGENTS.md`.

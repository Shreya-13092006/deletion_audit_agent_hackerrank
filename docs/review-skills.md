# Review Skills and Subagents — Deletion Audit Agent

There are three project skills in `.claude/skills/`, two subagents in `.claude/agents/`, and one helper tool, `.claude/tools/recovery_sandbox.py`. Both subagents are owned by `/architecture-challenger`:
- **`failure-recovery`** makes candidate fixes inside a **temporary sandbox copy** of the current project. The copy works with uncommitted and untracked files: no commit, branch, stash or git worktree is needed.
- **`change-validator`** checks those fixes read-only.

Adoption order is fixed: **recovery → isolation verified → validation APPROVE → your approval → adoption.**

```
                ┌──────────────── fix requests (evaluation / release findings) ───────────────┐
                ▼                                                                               │
/architecture-challenger ───────────────► /independent-evaluator ───────────► /integration-release
  main context: analysis, decisions,        skeptical recomputation,           go / no-go gate
  your approval, adoption                   read-only on product code
        │
        │ recovery_sandbox.py create --id <id>
        ▼
  .claude/sandboxes/<id>/   base/ (read-only snapshot)   work/ (editable copy, dataset/ read-only)
                            manifest.json (git HEAD/branch/dirty files, sha256 of copied + main files)
        │ brief
        ▼
  failure-recovery subagent  (Read/Grep/Glob/Bash/Edit/Write; edits and runs ONLY in work/)
  reproduce → isolate → fix + regression test → rerun → keep or roll back (restore from base/)
        │ Recovery result → recovery_sandbox.py diff → changes.patch + changed_files.json
        │ recovery_sandbox.py verify → main project unchanged? base + dataset fixture intact?
        ▼
  change-validator subagent  (Read/Grep/Glob/Bash, no Edit/Write)
  verify → own diff (git diff --no-index base work) → checks → re-measure in work → re-check
        │ APPROVE | REJECT
        ▼ APPROVE only
  /architecture-challenger asks you → recovery_sandbox.py apply --approved-by-user (drift check + backup)
  → re-measure main project → restore from backup if worse
        │
        ▼ recovery_sandbox.py preserve → docs/reviews/recovery-artifacts/<id>/ → recovery_sandbox.py cleanup
```

## Why a sandbox copy instead of a git worktree

- **A worktree contains only committed files.** This project's solution is uncommitted, so a worktree would start from the empty starter files.
- **The sandbox copies the current files, then records two things:**
  - the exact source state (git HEAD, branch, dirty and untracked files)
  - the sha256 of every copied file and every main-project file
- **Isolation is verified, not assumed.** `verify` re-hashes the main project and fails on any change (generated outputs and `log.txt` excepted). It also checks that `base/` and the read-only dataset fixture are intact.
- **The diff is reliable without git.** It is hash-based (`changed_files.json`) plus a unified patch (`changes.patch`), and the validator cross-checks both with its own `git diff --no-index`.
- **Adoption is a guarded copy:**
  - only user-approved files
  - each target must still match its hash at sandbox creation (no drift)
  - each original is backed up first
  - deletions are never applied automatically
- **Cleanup is guarded:** it deletes only `.claude/sandboxes/<id>/`, and only after the preserved artifacts' hashes are confirmed.

**Isolation boundary (be precise):**
- Every **change** to the main project is *detected* (`verify`), and a run stops on ISOLATION FAILED.
- *Preventing* a subagent from writing outside the sandbox relies on its instructions, unless the guard hook in `docs/agent-safety-proposal.md` is installed.
- A failed run never leads to adoption, and the sandbox is kept as evidence.

## Rules everything shares

- Follow `AGENTS.md`: every skill and subagent appends a `log.txt` turn entry with valid `tool=` and `model=` lines. Subagents set `parent_agent=architecture-challenger`. `log.txt` lives only in the main project root; it is the single allowed write outside a sandbox.
- Never modify `dataset/`. Never use organizer-only data. Never expose secrets. Never stage, commit, reset, stash or push unless you ask.
- Never fabricate evidence, records, identifiers or citations. Never cite evidence captured after `audit_at`. Never silently turn an uncertain case into COMPLETE.
- Preserve:
  - determinism (identical `output.csv` sha256)
  - identity safeguards (no linking by name)
  - audit-time cutoffs and the freshness horizon
  - policy rules
  - evidence provenance
  - output ordering
- Quote numbers from fresh runs only. Don't present sample scores as hidden-test accuracy; the samples were also used for tuning.

**Standard measurement commands** (run from the project root or from a sandbox's `work/`):
```
python -m unittest discover -s code/tests -t code/tests
python code/evaluation/main.py [-v]        # 32 sample cases vs dataset/sample_output.csv
python code/evaluation/main.py --custom    # hand-built custom cases
python code/main.py                        # full 518-case run -> output.csv (run twice: same sha256)
```

---

## `recovery_sandbox.py` (`.claude/tools/recovery_sandbox.py`)

| Command | Writes to | Purpose |
|---|---|---|
| `create --id ID` | `.claude/sandboxes/ID/` only | Copies `code/`, `dataset/` (read-only), `README.md`, `AGENTS.md`, `CLAUDE.md` and `problem_statement.md`. Excludes `.git`, `.env`, `settings.local.json`, caches, `output.csv` and `log.txt`. Stops if a secret pattern is found. Writes `manifest.json`. |
| `verify --id ID` | nothing | Isolation proof: main-project hashes unchanged, `base/` and dataset fixture intact. Exit 1 on failure. |
| `diff --id ID` | the sandbox | Writes `changes.patch` and `changed_files.json` (base vs work). Stops on binary or non-UTF-8 changes. |
| `preserve --id ID` | `docs/reviews/recovery-artifacts/ID/` | Copies the manifest, patch, change list and reports, then checks each copy's hash. |
| `apply --id ID --approved-by-user --files …` | the listed main-project files + `…/ID/backup/` | Parent only, after your approval. Includes the drift check, the backup and post-copy hash checks. |
| `cleanup --id ID` | removes `.claude/sandboxes/ID/` | Only after `preserve`, with the preserved hashes re-checked. Never touches main files. |

Exit code 2 means **BLOCKER**: isolation or diff reliability can't be guaranteed, so the workflow stops and reports it. `.claude/sandboxes/` is excluded from git locally through `.git/info/exclude`.

## 1. `/architecture-challenger` (first; owns both subagents)

**Analysis (§1–§5):**
- Measures the baseline.
- Finds bottlenecks and gaps.
- Compares four designs: deterministic, parallel workers, specialized agents and hybrid.
- Maps which stages are parallel-safe and which must stay sequential.
- Writes a reversible migration plan.

**Preflight and delegation (§6):**
1. `create` the sandbox, then `verify` it.
2. Brief `failure-recovery` (Agent tool, `subagent_type: "failure-recovery"`, no `isolation`).
3. When it returns, run `diff`, then `verify`. ISOLATION FAILED means stop, report, and keep the sandbox.

**Validation (§7):** briefs `change-validator`. On REJECT it retries at most twice, or records a limitation.

**Adoption (§8):**
- Only after APPROVE: asks you, runs `apply --approved-by-user`, re-measures, and restores from backup if worse.
- Never stages or commits.
- Then runs `preserve`, followed by `cleanup`.

**Output:** `docs/reviews/architecture-YYYY-MM-DD.md` and `docs/reviews/recovery-YYYY-MM-DD.md`, plus the raw artifacts in `docs/reviews/recovery-artifacts/<id>/`.

## `failure-recovery` subagent (`.claude/agents/failure-recovery.md`)

**Tools:** Read, Grep, Glob, Bash, Edit, Write. **Works in:** `.claude/sandboxes/<id>/work/` only, never in `base/`, never in `work/dataset/`.

**What it does:**
1. Measures a baseline in `work/`.
2. Classifies each failure: root cause, severity and certainty.
3. Reproduces it with the smallest check, then bisects parse → identity → link → state → policy → plan → validate.
4. Applies the narrowest evidence-grounded fix, one failure at a time, with a regression test.
5. Rolls back by restoring from `base/`.
6. Writes `reports/recovery-result.md` and runs `diff`.

When the data cannot decide, the result is a flag plus a documented limitation, never a guessed fix.

**Returns:** a "Recovery result" naming the sandbox id, the work dir and the source HEAD/branch from the manifest. Its "Changes to adopt" must match `changed_files.json`.

## `change-validator` subagent (`.claude/agents/change-validator.md`)

**Tools:** Read, Grep, Glob and Bash; no Edit or Write. **Spawned by:** `/architecture-challenger` only.

**It may not run** `diff`, `preserve`, `apply` or `cleanup`. **Only writes:** its `log.txt` entry and generated measurement artifacts inside `work/`.

**What it does:**
1. Runs `verify`. ISOLATION OK is required.
2. Computes its own diff with `git diff --no-index base/code work/code` and cross-checks it against `changed_files.json` and the recovery's list.
3. Inspects the diff:
   - no dataset or expected-answer changes
   - every change within scope
   - no hard-coded ids
   - no uncertain case became COMPLETE
   - no late citations are possible
   - safeguards are intact
   - no secrets
   - every fix has a regression test
4. Re-measures twice in `work/`.
5. Re-checks the diff set and runs `verify` again.

**Returns:** "Validation verdict: APPROVE | REJECT". The parent saves it to `reports/validation-verdict.md`.

## 2. `/independent-evaluator` (second)

**Purpose:** a skeptical evaluator, not an agreeable code reviewer.

**What it does:**
- Recomputes expected results with its own standard-library scripts over raw `dataset/` files, never importing `code/audit`.
- Checks identity, citations, timestamps, states versus `deletion_rules.csv`, ordering and contract, and COMPLETE proof.
- Proposes edge, adversarial and regression cases.

**Never** changes expected answers, test assertions or product code.

**Output:** `docs/reviews/evaluation-YYYY-MM-DD.md`. Critical and major findings go back through `/architecture-challenger <report>`.

## 3. `/integration-release` (last)

**What it does:**
- Reconciles the review reports. Priority order:
  1. correctness and safety
  2. measured accuracy
  3. simplicity
  4. latency and cost
- Blocks any adoption that lacks both a validator APPROVE and your recorded approval.
- Runs the full verification twice.
- Works through a PASS/FAIL checklist covering `output.csv`, tests, the reports, `code.zip`, the README, `log.txt` and an untouched `dataset/`.
- Builds a baseline comparison table.

**Decision:** **BLOCK** or **GO**.

**Output:** `docs/reviews/release-YYYY-MM-DD.md`

---

## Files

| Component | File |
|---|---|
| `/architecture-challenger` skill | `.claude/skills/architecture-challenger/SKILL.md` |
| `failure-recovery` subagent | `.claude/agents/failure-recovery.md` |
| `change-validator` subagent | `.claude/agents/change-validator.md` |
| Sandbox tool | `.claude/tools/recovery_sandbox.py` |
| `/independent-evaluator` skill | `.claude/skills/independent-evaluator/SKILL.md` |
| `/integration-release` skill | `.claude/skills/integration-release/SKILL.md` |
| Protections proposal | `docs/agent-safety-proposal.md` |
| `/interview` skill (existing) | `.claude/skills/interview/SKILL.md` |

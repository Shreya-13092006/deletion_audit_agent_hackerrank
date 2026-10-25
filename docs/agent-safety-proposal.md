# Agent Safety Proposal — Enforceable Protections and Feature-Branch Baseline

_Status: PROPOSAL. Prepared 2026-10-25._

> **Update (2026-10-25): recovery no longer depends on git worktrees.** It now uses temporary sandbox copies made by `.claude/tools/recovery_sandbox.py` (see `docs/review-skills.md`). Those copies work with uncommitted and untracked files, so the feature-branch baseline in §5 is **optional**; no commit is needed for recovery to work.
>
> **Already done from §5:** branch `solution-baseline` was created and 62 files were staged, but nothing was committed; `worktree.baseRef: "head"` was set in `.claude/settings.local.json`.
>
> **The §2 and §3 protections still apply, with two adjustments for sandboxes under `.claude/sandboxes/`:**
> - Don't put `Edit(.claude/**)` in `ask`. It would prompt on every sandbox edit; protect `.claude/agents` and `.claude/skills` with narrower rules instead.
> - Whether `Edit(code/**)` also matches `.claude/sandboxes/<id>/work/code/**` is UNVERIFIED (U2).
>
> **The guard hook could add prevention**, not just `verify`'s detection: while a sandbox run is active, deny Edit and Write outside `.claude/sandboxes/<id>/`, except for `log.txt`.

## 1. Verified facts this proposal relies on

Sources:
- **[cfg]** the Claude Code settings reference loaded in-session via the `update-config` skill (settings JSON schema and hook docs)
- **[test]** pipe-tests run in this session in the system temp folder, outside the repo

| # | Fact | Source |
|---|---|---|
| F1 | Path rules use `Edit(path)` for every file-writing tool (Write, Edit, NotebookEdit). `Write(path)` path rules are **not** matched by file permission checks. | cfg |
| F2 | Bash rules support exact and prefix-wildcard forms: `Bash(git push *)` matches `git push …`. | cfg |
| F3 | `permissions` has `allow`, `ask` and `deny` arrays, plus `defaultMode` (`default`, `acceptEdits`, `auto`, `plan`, `dontAsk`, `bypassPermissions`) and `disableBypassPermissionsMode`. | cfg |
| F4 | A PreToolUse hook can block a tool call by printing `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"…"}}`. Exit code 2 is a blocking error. | cfg |
| F5 | A hook's `onFailure: "block"` makes a hook crash or timeout count as exit 2, so the call is blocked rather than allowed. The default `continue` lets the call proceed. | cfg |
| F6 | Hooks can be filtered with `if` using permission-rule syntax, e.g. `"if": "Bash(git *)"`. | cfg |
| F7 | `worktree.baseRef` controls where agent-isolation worktrees branch from. The default `fresh` uses **origin/&lt;default-branch&gt;**; `head` uses the **current local HEAD**. | cfg |
| F8 | Settings load in the order user → project (`.claude/settings.json`) → local (`.claude/settings.local.json`). A malformed settings file silently disables **all** settings from that file. | cfg |
| F9 | `.claude/settings.local.json` is ignored by your global git ignore (`~/.config/git/ignore`: `**/.claude/settings.local.json`). | `git check-ignore -v` |
| F10 | The draft guard hook (§3) returned the expected decision in 14 of 14 synthetic cases, and exits 1 on malformed input. | test |
| F11 | `origin` is `https://github.com/interviewstreet/hackerrank-orchestrate-october26.git`, the organizers' public repository. | `git remote -v` |

**UNVERIFIED (test after installing; don't rely on these until tested):**
- **U1:** precedence when one call matches both an `ask` and an `allow` rule. Claude Code docs state deny > ask > allow; not tested here.
- **U2:** whether a relative rule like `Edit(dataset/**)` is anchored to the project root, and whether it also matches the same path inside `.claude/worktrees/<name>/`. The hook in §3 covers both regardless.
- **U3:** whether PreToolUse hooks and permission rules from `.claude/settings.local.json` apply to tool calls made *inside subagents*. They are expected to, but this wasn't observed.
- **U4:** whether sandboxing (which would extend Edit deny rules to Bash writes) is available on this native-Windows setup. It isn't proposed here.

## 2. Proposed permission rules (merge into `.claude/settings.local.json`; don't replace)

The current file has 4 `allow` entries. Keep them, but note the risk: `Bash(python3 *)` auto-approves **every** `python3` command, including ones that write files. Consider moving it to `ask`, or narrowing it to the four measurement commands.

```json
{
  "permissions": {
    "deny": [
      "Edit(dataset/**)",
      "Bash(git push *)",
      "Bash(git reset --hard *)",
      "Bash(git clean *)",
      "Bash(git rebase *)",
      "Bash(git filter-branch *)"
    ],
    "ask": [
      "Bash(git commit *)",
      "Bash(git add *)",
      "Bash(git switch *)",
      "Bash(git checkout *)",
      "Bash(git restore *)",
      "Bash(git stash *)",
      "Bash(git merge *)",
      "Bash(git apply *)",
      "Bash(git branch *)",
      "Bash(git worktree *)",
      "Edit(code/**)",
      "Edit(output.csv)",
      "Edit(.claude/**)"
    ],
    "disableBypassPermissionsMode": "disable"
  },
  "worktree": { "baseRef": "head" }
}
```

**Why each part:**
- **`Edit(dataset/**)` deny:** the dataset is read-only (F1: `Edit()` covers Write too).
- **`git push` deny:** pushing would publish to the organizers' repository (F11).
- **`ask` on commit, branch and checkout operations and on edits to `code/**`:** this is your approval gate, enforced by the permission system rather than by skill text.
- **`worktree.baseRef: "head"`:** without it, recovery worktrees start from `origin/main`, the empty starter files, even after you commit locally (F7).

**Side effect to test (U2):** recovery worktrees live under `.claude/worktrees/<name>/`. If `Edit(.claude/**)` matches those paths, every edit the recovery subagent makes will prompt you. That is safe but noisy. If it happens, drop `Edit(.claude/**)` and protect the agent and skill files with the hook instead.

**Mode caveat:** these prompts protect you only in `default` or `plan` mode. `acceptEdits` auto-accepts Edit, so the `ask` rules on `code/**` may be skipped (UNVERIFIED), and `auto` routes decisions through a classifier. Run the review chain in `default` mode.

## 3. Proposed PreToolUse guard hook (defense in depth for Bash and PowerShell)

Permission rules can't see *what a shell command writes*. The guard inspects the command text and the file paths.

**Install location (proposed):** `.claude/hooks/guard_hook.py`. Settings to merge:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit|Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -I \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_hook.py\"",
            "timeout": 10,
            "onFailure": "block",
            "statusMessage": "Project guard"
          }
        ]
      }
    ]
  }
}
```

`$CLAUDE_PROJECT_DIR` resolving inside the hook command is UNVERIFIED on this Windows / Git Bash setup. If it doesn't resolve, use the absolute path.

**Script, exactly as pipe-tested (F10):**

```python
"""PreToolUse guard: deny writes to dataset/ and destructive or publishing git commands.
Reads the hook JSON on stdin; prints a deny decision as JSON or nothing (no opinion)."""
import json
import re
import sys

DATASET_PATH = re.compile(r"(^|/)dataset/", re.I)
GIT_DENY = re.compile(r"\bgit\s+(push|reset\s+--hard|clean\s+-[a-z]*f|rebase|filter-branch|update-ref|"
                      r"branch\s+-D|worktree\s+remove\s+--force)\b", re.I)
WRITE_VERB = re.compile(r"(>>?|\btee\b|\brm\b|\bmv\b|\bcp\b|\bsed\s+-i|\bgit\s+(checkout|restore|rm|mv|apply)\b|"
                        r"Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|New-Item|"
                        r"open\([^)]*['\"][wax+])", re.I)
DATASET_IN_CMD = re.compile(r"dataset[\\/]", re.I)


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


data = json.load(sys.stdin)
tool, inp = data.get("tool_name", ""), data.get("tool_input") or {}
if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
    path = (inp.get("file_path") or inp.get("notebook_path") or "").replace("\\", "/")
    if DATASET_PATH.search(path):
        deny("dataset/ is read-only for this project (AGENTS.md)")
elif tool in ("Bash", "PowerShell"):
    cmd = inp.get("command", "")
    if GIT_DENY.search(cmd):
        deny("destructive or publishing git command blocked by project guard; run it yourself if intended")
    if DATASET_IN_CMD.search(cmd) and WRITE_VERB.search(cmd):
        deny("command appears to write under dataset/ (project guard)")
```

**Pipe-test results (F10):**

| Input | Result |
|---|---|
| `Edit` of `…\dataset\deletion_rules.csv` | deny |
| `Edit` of `dataset/` inside a worktree path | deny |
| `Write` of `code\audit\state.py` | no-opinion |
| `Write` of `docs\dataset-observations.md` | no-opinion (only the `dataset/` directory is protected) |
| `Remove-Item dataset\evidence` | deny |
| `echo x > dataset/output.csv` | deny |
| `python -c "open('dataset/a','w')"` | deny |
| `grep … dataset/…` (read) | no-opinion |
| `python code/main.py` | no-opinion |
| `git push` | deny |
| `git reset --hard` | deny |
| `git commit` | no-opinion (handled by the `ask` rule) |
| `git status` | no-opinion |
| Malformed stdin | exit 1, blocked under `onFailure: "block"` |

**Known limitation:** a script that writes into `dataset/` from its own code (e.g. `python some_script.py`) can't be detected from the command text. Only an OS-level control can stop that: a read-only file attribute on `dataset/`, or the sandbox (U4).

**Verification after install:**
1. Validate the JSON with `jq -e '.hooks.PreToolUse[] | .hooks[] | .command' .claude/settings.local.json`.
2. Open `/hooks` once, or restart, so the settings are reloaded.
3. Try an Edit of `dataset/x` (it must be denied), `git push --dry-run` (denied) and `git status` (allowed).
4. Repeat one denied call from inside a subagent to resolve U3.

## 4. Git hygiene: what to commit and what to exclude

**Current state:**
- branch `main` at `acb3dfc`
- 3 modified tracked files: `README.md`, `code/main.py`, `code/evaluation/main.py`
- 63 untracked files
- the secret scan of all untracked and modified files found no API keys, tokens or private keys, and there is no `.env`
- the only local path is `repo_root=C:/Users/shoer/...` in `log.txt`, which `AGENTS.md` requires

**Propose to commit (explicit paths only; never `git add -A`):**

| Group | Paths | Why |
|---|---|---|
| Solution code | `code/main.py`, `code/audit/**/*.py`, `code/tools/extract_images.py`, `code/tools/ocr_windows.ps1`, `code/requirements.txt` | The pipeline the worktrees need |
| Evaluation | `code/evaluation/main.py`, `code/evaluation/custom_cases.py`, `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md` | Required deliverables |
| Tests | `code/tests/*.py` | Regression suite |
| Reproducibility caches | `code/cache/image_facts.json`, `code/cache/ocr_raw/*.json`, `code/cache/intent_cache.json` | Screenshot facts (fictional data); needed for deterministic offline runs |
| Docs and config | `README.md`, `.gitignore`, `docs/*.md` | Instructions, observations and this proposal |
| Agent setup | `.claude/agents/*.md`, `.claude/skills/*/SKILL.md` | So the chain survives clones and worktrees |

**Propose to exclude** (add to `.gitignore`):

```
output.csv
sample_predictions.csv
code/cache/audit_trail*.jsonl
code/cache/llm_usage.json
code/cache/vision_cache.json
code/cache/image_extraction_trail.jsonl
log.txt
```

**Reasons:**
- `output.csv` and the trails are regenerated by every run; committing them makes every measurement look like a diff.
- `log.txt` is appended continuously by every agent. `AGENTS.md` requires one shared log at the main root, so keeping it out of worktrees prevents divergent copies. Submit it from the main tree.

`.claude/settings.local.json` is already ignored globally (F9). `dataset/` is tracked and unchanged; leave it as it is.

## 5. Feature-branch baseline plan (for your approval; nothing done yet)

1. **Start from a clean point.** Run `git status` (expected: the changes listed in §4) and `git stash list` (expected: empty).
2. **Create the branch:** `git switch -c solution-baseline`. This needs your approval: it's in the `ask` list once §2 is installed.
3. **Update `.gitignore`** with the §4 exclude lines.
4. **Stage the §4 commit list by explicit path.** Then check the staged set: `git diff --cached --stat`, and rerun the secret scan on `git diff --cached`.
5. **Commit with your approval.** Commit message: "Solution baseline: deletion-audit pipeline, tests, evaluation, agent setup".
6. **Set `worktree.baseRef: "head"`** in `.claude/settings.local.json` (§2), so isolation worktrees branch from this local commit. **Never push to `origin`**, the organizers' repository (F11).
7. **Verify in a fresh session:**
   - `git ls-files code/audit/pipeline.py` prints the path
   - run `failure-recovery` with a no-op brief ("measure baseline only, change nothing")
   - confirm its worktree contains `code/audit/` and that its numbers match the main tree
   - confirm the worktree is removed or left unchanged afterwards
8. **Rollback if needed:** `git switch main`. The branch can be deleted with `git branch -D solution-baseline`; nothing in the working tree is lost, because the files were already on disk.

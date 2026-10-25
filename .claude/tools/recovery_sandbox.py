"""Temporary-copy isolation for the failure-recovery workflow (no git commit or worktree needed).

Each sandbox lives in <project>/.claude/sandboxes/<id>/ and contains:
  base/            pristine read-only copy of the project state at creation (diff reference)
  work/            the copy recovery may edit and test in
  manifest.json    source state: git HEAD/branch/dirty status, sha256 of every copied file,
                   sha256 of every main-project file (to prove the main project was not touched)
  reports/         where the recovery and validator subagents write their reports
  changes.patch, changed_files.json   produced by `diff`
  preserved.json   produced by `preserve` once artifacts are copied to docs/reviews/

Commands (run from the project root):
  python .claude/tools/recovery_sandbox.py create  --id ID
  python .claude/tools/recovery_sandbox.py verify  --id ID      # isolation checks, exit 1 on failure
  python .claude/tools/recovery_sandbox.py diff    --id ID      # base vs work -> patch + file list
  python .claude/tools/recovery_sandbox.py preserve --id ID     # copy artifacts to docs/reviews/recovery-artifacts/ID/
  python .claude/tools/recovery_sandbox.py apply   --id ID --files a b --approved-by-user   # parent only, after approval
  python .claude/tools/recovery_sandbox.py cleanup --id ID      # only after preserve; never touches main files

Safety properties:
  * the main project is never written except by `preserve` (docs/reviews/recovery-artifacts/ID/) and by
    `apply` (only the listed, user-approved files, after a drift check and a backup);
  * dataset/ is copied as a read-only fixture and its hashes are re-checked;
  * .git, secrets (.env, settings.local.json), caches and generated outputs are never copied;
  * any condition that makes isolation or the diff unreliable stops with exit code 2 (BLOCKER).
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SANDBOXES = PROJECT / ".claude" / "sandboxes"
ARTIFACTS = PROJECT / "docs" / "reviews" / "recovery-artifacts"

# What a sandbox needs to build, test and evaluate the solution.
COPY_ROOTS = ["code", "dataset", "README.md", "AGENTS.md", "CLAUDE.md", "problem_statement.md"]
# Never copied, never diffed, never counted as a main-project change.
EXCLUDE_PARTS = {".git", "__pycache__", ".venv", "venv", "node_modules", "sandboxes", "worktrees"}
EXCLUDE_NAMES = {".env", "settings.local.json", "code.zip"}
GENERATED = re.compile(r"^(output\.csv|sample_predictions\.csv|log\.txt|"
                       r"code/cache/(audit_trail.*\.jsonl|llm_usage\.json|vision_cache\.json|"
                       r"image_extraction_trail\.jsonl))$")
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
                    r"ANTHROPIC_API_KEY\s*=\s*['\"]?[A-Za-z0-9]")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class Blocker(Exception):
    """Isolation or diff reliability cannot be guaranteed."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def excluded(relpath: str) -> bool:
    parts = relpath.split("/")
    return bool(set(parts) & EXCLUDE_PARTS) or parts[-1] in EXCLUDE_NAMES or bool(GENERATED.match(relpath))


def walk(root: Path, roots=None) -> dict[str, Path]:
    """Relative posix path -> absolute path for every included file under root."""
    out: dict[str, Path] = {}
    starts = [root / r for r in roots] if roots else [root]
    for start in starts:
        if start.is_file():
            r = rel(start, root)
            if not excluded(r):
                out[r] = start
            continue
        if not start.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_PARTS)
            for name in sorted(filenames):
                p = Path(dirpath) / name
                r = rel(p, root)
                if not excluded(r):
                    out[r] = p
    return out


def main_project_files() -> dict[str, Path]:
    """Every main-project file the sandbox must not change (dataset included)."""
    return {r: p for r, p in walk(PROJECT).items() if not r.startswith(".claude/sandboxes/")}


def box(sid: str) -> Path:
    if not ID_RE.match(sid):
        raise Blocker(f"invalid sandbox id {sid!r}")
    root = (SANDBOXES / sid).resolve()
    if SANDBOXES.resolve() not in root.parents:
        raise Blocker("sandbox path escapes .claude/sandboxes")
    return root


def git(*args) -> str:
    res = subprocess.run(["git", "-C", str(PROJECT), *args], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else f"<git error: {res.stderr.strip()[:120]}>"


def make_readonly(path: Path) -> None:
    for p in [path] if path.is_file() else [Path(d) / f for d, _, fs in os.walk(path) for f in fs]:
        os.chmod(p, stat.S_IREAD)


def make_writable(path: Path) -> None:
    for d, _, fs in os.walk(path):
        for f in fs:
            os.chmod(Path(d) / f, stat.S_IREAD | stat.S_IWRITE)


# ---- commands --------------------------------------------------------------------------------
def cmd_create(sid: str) -> int:
    root = box(sid)
    if root.exists():
        raise Blocker(f"sandbox {sid} already exists")
    files = walk(PROJECT, COPY_ROOTS)
    if "code/main.py" not in files or not any(r.startswith("code/audit/") for r in files):
        raise Blocker("solution code not found in the project; nothing to isolate")
    for r, p in files.items():
        if p.suffix.lower() in {".py", ".md", ".txt", ".json", ".ps1", ".csv", ".log", ".sql"} \
                and not r.startswith("dataset/") and SECRET.search(p.read_text(encoding="utf-8", errors="ignore")):
            raise Blocker(f"possible secret in {r}; refusing to copy")
    for sub in ("base", "work"):
        for r, p in files.items():
            dest = root / sub / r
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
    (root / "reports").mkdir()
    make_readonly(root / "base")
    make_readonly(root / "work" / "dataset")
    manifest = {
        "id": sid,
        "created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_project": str(PROJECT),
        "git": {"head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
                "status_porcelain": git("status", "--porcelain", "--untracked-files=all").splitlines()},
        "copied_files": {r: sha256(p) for r, p in files.items()},
        "main_project_files": {r: sha256(p) for r, p in main_project_files().items()},
        "excluded_rules": {"parts": sorted(EXCLUDE_PARTS), "names": sorted(EXCLUDE_NAMES),
                           "generated": GENERATED.pattern},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    copied = len(files)
    print(f"created {root}\n  copied files: {copied} (dataset read-only: "
          f"{sum(r.startswith('dataset/') for r in files)})\n  work dir: {root / 'work'}")
    return 0


def load_manifest(root: Path) -> dict:
    path = root / "manifest.json"
    if not path.exists():
        raise Blocker("manifest.json missing: the source state cannot be proven")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_verify(sid: str) -> int:
    root = box(sid)
    m = load_manifest(root)
    problems = []
    now = {r: sha256(p) for r, p in main_project_files().items()}
    before = m["main_project_files"]
    for r in sorted(set(before) | set(now)):
        if r.startswith("docs/reviews/recovery-artifacts/"):
            continue                      # written by `preserve`, expected
        if before.get(r) != now.get(r):
            problems.append(f"MAIN PROJECT CHANGED: {r}")
    for r, h in m["copied_files"].items():
        b = root / "base" / r
        if not b.exists() or sha256(b) != h:
            problems.append(f"base copy changed: {r}")
        if r.startswith("dataset/"):
            w = root / "work" / r
            if not w.exists() or sha256(w) != h:
                problems.append(f"dataset fixture changed in work copy: {r}")
    for p in problems:
        print(p)
    print("ISOLATION OK" if not problems else f"ISOLATION FAILED ({len(problems)} problems)")
    return 0 if not problems else 1


def cmd_diff(sid: str) -> int:
    root = box(sid)
    m = load_manifest(root)
    base, work = walk(root / "base"), walk(root / "work")
    changes, patch = [], []
    for r in sorted(set(base) | set(work)):
        if r.startswith("dataset/"):
            continue                      # verified separately; never part of a proposal
        b, w = base.get(r), work.get(r)
        hb, hw = (sha256(b) if b else None), (sha256(w) if w else None)
        if hb == hw:
            continue
        kind = "added" if b is None else "deleted" if w is None else "modified"
        changes.append({"path": r, "change": kind, "sha256_before": hb, "sha256_after": hw,
                        "sha256_source_at_creation": m["copied_files"].get(r)})
        try:
            old = b.read_text(encoding="utf-8").splitlines(keepends=True) if b else []
            new = w.read_text(encoding="utf-8").splitlines(keepends=True) if w else []
        except UnicodeDecodeError as exc:
            raise Blocker(f"binary or non-UTF-8 change in {r}; a reviewable text diff cannot be produced") from exc
        patch.extend(difflib.unified_diff(old, new, f"a/{r}" if b else "/dev/null", f"b/{r}" if w else "/dev/null"))
    (root / "changes.patch").write_text("".join(patch), encoding="utf-8")
    (root / "changed_files.json").write_text(json.dumps(changes, indent=1), encoding="utf-8")
    print(f"{len(changes)} changed file(s); patch: {root / 'changes.patch'}")
    for c in changes:
        print(f"  {c['change']:8} {c['path']}")
    return 0


def cmd_preserve(sid: str) -> int:
    root = box(sid)
    load_manifest(root)
    if not (root / "changes.patch").exists():
        raise Blocker("run `diff` before `preserve`")
    dest = ARTIFACTS / sid
    dest.mkdir(parents=True, exist_ok=True)
    items = ["manifest.json", "changes.patch", "changed_files.json"]
    items += [f"reports/{p.name}" for p in sorted((root / "reports").glob("*")) if p.is_file()]
    record = {}
    for item in items:
        src, out = root / item, dest / item
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        if sha256(src) != sha256(out):
            raise Blocker(f"copy verification failed for {item}")
        record[item] = sha256(out)
    (root / "preserved.json").write_text(json.dumps({"dest": str(dest), "files": record}, indent=1), encoding="utf-8")
    print(f"preserved {len(record)} artifact(s) to {dest}")
    return 0


def cmd_apply(sid: str, files: list[str], approved: bool) -> int:
    if not approved:
        raise Blocker("apply requires --approved-by-user (explicit user approval recorded by the parent)")
    root = box(sid)
    m = load_manifest(root)
    changes = {c["path"]: c for c in json.loads((root / "changed_files.json").read_text(encoding="utf-8"))}
    backup = ARTIFACTS / sid / "backup"
    for r in files:
        if r not in changes:
            raise Blocker(f"{r} is not in changed_files.json")
        if r.startswith("dataset/") or excluded(r):
            raise Blocker(f"{r} may not be adopted")
        target = PROJECT / r
        expected = m["main_project_files"].get(r)
        actual = sha256(target) if target.exists() else None
        if actual != expected:
            raise Blocker(f"{r} changed in the main project since the sandbox was created; resolve manually")
    for r in files:
        target, c = PROJECT / r, changes[r]
        if target.exists():
            (backup / r).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup / r)
        if c["change"] == "deleted":
            print(f"skip delete of {r}: deletions are reported, never applied automatically")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / "work" / r, target)
        if sha256(target) != c["sha256_after"]:
            raise Blocker(f"post-copy hash mismatch for {r}; restore from {backup / r}")
        print(f"adopted {r} (backup: {backup / r if (backup / r).exists() else 'new file'})")
    return 0


def cmd_cleanup(sid: str) -> int:
    root = box(sid)
    rec_path = root / "preserved.json"
    if not rec_path.exists():
        raise Blocker("artifacts not preserved; refusing to delete the sandbox")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    for item, h in rec["files"].items():
        out = Path(rec["dest"]) / item
        if not out.exists() or sha256(out) != h:
            raise Blocker(f"preserved artifact missing or altered: {out}")
    if PROJECT.resolve() == root or root in PROJECT.resolve().parents or SANDBOXES.resolve() not in root.parents:
        raise Blocker("refusing to delete a path outside .claude/sandboxes")
    make_writable(root)
    shutil.rmtree(root)
    print(f"removed {root} (artifacts kept in {rec['dest']})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["create", "verify", "diff", "preserve", "apply", "cleanup"])
    ap.add_argument("--id", required=True)
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--approved-by-user", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.command == "apply":
            return cmd_apply(args.id, args.files, args.approved_by_user)
        return {"create": cmd_create, "verify": cmd_verify, "diff": cmd_diff,
                "preserve": cmd_preserve, "cleanup": cmd_cleanup}[args.command](args.id)
    except Blocker as exc:
        print(f"BLOCKER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

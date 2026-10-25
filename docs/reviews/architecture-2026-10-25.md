# Architecture review: 2026-10-25

**Scope:** `/architecture-challenger`, asked for a design assessment and changes for better latency, reliability, scalability and cost.

This is a read-only review. No code was changed and no sandbox was created. §6–§8 are deferred: the standing user instruction is "research and report first; wait for my approval before implementation", and none of the delegation triggers fired (no failing tests, no regressions, no validation problems).

## 1. Measured baseline

All numbers were measured in this session.

| Check | Result |
|---|---|
| `python -m unittest discover -s code/tests -t code/tests` | **59/59 pass** (1.75 s) |
| `python code/evaluation/main.py` (32 samples) | status **1.000** · step P/R/F1 **0.995 / 0.948 / 0.971** · evidence **1.000** · sequence **0.688** |
| Failing sample cases | case_03, 04, 18, 20, 21, 23, 25, 26, 27, 28 |
| `python code/evaluation/main.py --custom` | **6/6 pass** |
| `python code/main.py --no-llm --out <tmp>`, run twice | 518 rows; 355 INCOMPLETE / 153 COMPLETE / 10 NOT_APPLICABLE; **0 validation problems** |
| Determinism | sha256 `7a9683fd…ea50` on both runs, identical to the root `output.csv` |
| Wall-clock time, full run | **≈1.9 s** |
| Model calls / cost | **0 / $0.00**. All 518 intents were decided by rule (`intent:rule` = 518 in the audit trail) |

The full runs were written to a temp path. The root `output.csv`, `audit_trail.jsonl` and `llm_usage.json` were confirmed byte-identical afterwards.

**Stage timing** (unprofiled, `time.perf_counter`):

| Stage | Time | Share |
|---|---|---|
| `Auditor.__init__`: parse 94 files + 4,011 activity rows into 3,050 observations | 0.42 s | 24% |
| `assign_workflow_resources`: 550 cases | 0.61 s | 35% |
| Per-case `audit()` loop: 518 cases | 0.68 s | 39% |
| …of which `link_resources` alone | 0.53 s | (≈78% of the loop) |

**Hotspot.** cProfile shows 1.58 M calls each to `matches()` and `visible()`. `link_resources` (`code/audit/linker.py:28-35`) sorts and scans **all 3,050 observations for every case**, and it runs twice per case: once in attribution (`pipeline.py:85`) and once in `audit()` (`pipeline.py:181`). Together that is about 1.05 s of the ≈1.7 s compute, roughly 60%.

## 2. Assessment of the current architecture

The design is a **deterministic, sequential, evidence-first pipeline**:

> parse → identity graph → link → intent → global workflow attribution → state at `audit_at` → policy → planner → validate

It is the right shape for this problem. These properties are correct and should not change:

- **Rules decide; no model ever does.** The LLM is optional and fail-safe in two places only: the intent fallback (`intent.py:61-68`) and the vision extractor (`extract_images.py`).
- **Time-correct state.** `visible()` checks both `observed_at` and `captured_at`. Ownership and state are separated (`linker.py` docstring). A 14-day freshness horizon applies (`state.py:58-62`).
- **Deterministic output.** Sorted iteration everywhere, `sort_keys` JSON, and a stable planner sort key (`planner.py:38-40`).
- **Contract validation before writing** (`validate.py`), plus an append-only audit trail with per-case flags.

The weaknesses are the following, ordered by impact.

### 2.1 Accuracy bottlenecks: design limits, not bugs

Every remaining sample miss falls into one of three groups:

| Group | Cases | Can a change fix it? |
|---|---|---|
| Identity-less anonymized analytics records in shared workflow windows (true ties) | case_03, 21, 25, 26, 27, 28 (analytics) | No. Evidence support and time are tied, and guessing would assign one person's record to another. |
| Records absent from all participant data | case_04 (`account_004`), case_18, case_20 (`audit_record_*`) | No. Emitting them would mean inventing data. |
| Account picked by time proximity alone | case_23 | Only partially. Flagged; time proximity was 82% correct on the samples. |

Flag concentration on the 508 authorized eval cases (from `code/cache/audit_trail.jsonl`):

| Flag | Cases | Component |
|---|---|---|
| `ACCOUNT_FROM_WORKFLOW_ACTIVITY` | 252 | `assign_workflow_resources` |
| `RETAINED_RECORD_ONLY_IN_LATER_EVIDENCE` | 125 | `state.resolve` horizon |
| `STATE_UNKNOWN` | 84 | `state.resolve` horizon |
| `ACCOUNT_WORKFLOW_TIME_ONLY_TIE` | 64 | `assign_workflow_resources` |
| `ACCOUNT_UNRESOLVED` | 23 | `primary_account` |

**Hidden-set risk is concentrated in one component: workflow attribution** (252 cases, 64 decided by time alone). It is the only place where a heuristic, not evidence, picks a resource.

### 2.2 Missing components

- **Per-step confidence.** Flags exist per case only. A reviewer cannot tell which step came from workflow attribution and which from direct evidence. The provenance is already in the trail but not attached to steps.
- **Hold-out split.** All 32 samples were used for tuning (windows, horizon), so 0.971 F1 is not a generalization estimate. Nothing measures overfitting.
- **Per-component regression baseline.** Tests are unit-level. No snapshot pins, per case, the linked-resource set or the attribution picks, so a refactor that changes attribution would surface only as an end-to-end F1 delta.
- **An independent second extractor for screenshots.** OCR is the only extractor. The Anthropic path exists, but it overwrites `image_facts.json` in place (`extract_images.py:144,179`). It also skips closed-world validation (`rejected=[]`, line 167) and writes to the usage ledger.

### 2.3 Reliability

| Risk | Where | Severity |
|---|---|---|
| Windows-only re-extraction (`Windows.Media.Ocr` via PowerShell) | `extract_images.py`, `tools/ocr_windows.ps1` | Medium. The shipped cache makes runs portable, but re-extraction is not. |
| Silent parse failures: per-file exceptions go only to the trail and are not printed or counted in the exit status | `parsers/__init__.py:51-53`; `main.py` prints only validation problems | Medium. A corrupted file would quietly drop evidence. Currently 0 `parse_error` events. |
| Output depends on the environment: `AUDIT_STATE_MAX_AGE_DAYS` and the model env vars change results without appearing in `output.csv` or in the run line | `config.py:16-17,53` | Low–medium |
| Intent fail-safe returns `NOT_APPLICABLE` when undetermined. That is correct with no model, but a Haiku refusal would also land here on a real deletion | `intent.py:68-70` | Low today (0 undetermined) |
| `requirements.txt` has `anthropic>=1.0`, which now resolves to SDK 2.x (API version 2026-10-21) | `code/requirements.txt` | Low; the optional path only |
| Nondeterminism | — | **None found.** Two runs are byte-identical; the trail uses `sort_keys` and `default=sorted` |

### 2.4 Scalability

The per-case cost is **O(observations)**, because of the full scan plus sort in `link_resources`. The total cost is **O(cases × observations)**, paid twice.

Today that is 550 × 3,050 ≈ 1.7 M predicate calls, which is fine. At 10× data (≈5k cases, ≈30k observations) it becomes ≈150 M calls, **roughly 2–3 minutes**. This is an estimate, extrapolated linearly from 1.05 s at 1.7 M calls.

`cooccurrence()` (`pipeline.py:89-95`) also rebuilds the case's evidence set on every call, which is quadratic in a case's candidate count.

Memory is not a concern: the whole store is under 100 MB.

## 3. Alternatives compared

| Option | Accuracy | Latency (518 cases) | Cost/run | Reliability / determinism | Effort | Risk to working behavior |
|---|---|---|---|---|---|---|
| **A. Current deterministic sequential pipeline** | F1 0.971 / seq 0.688 (measured) | 1.9 s (measured) | $0 | Byte-identical runs; fail-safe defaults | — | — |
| **B. A + indexed linker + memoized links** (recommended) | Identical; the output hash must not change | ≈0.8–1.0 s (estimate: removes ≈1 s of the scan) | $0 | Same; a pure refactor guarded by a hash check | ~1 day | Low; the hash gate catches any drift |
| **C. Parallel workers** (per-file parse, per-case audit) | Identical if the merge is stable | Likely **slower** at this size: Windows `spawn` plus pickling a 3k-observation store costs ≈0.3–0.6 s per pool (estimate) | $0 | Needs per-case trail buffers and an ordered merge; more moving parts | ~1–2 days | Medium (shared `trail.entries` list, ordering) |
| **D. Specialized LLM agents** (intent, extraction, tie adjudication) | No gain on known misses: the ties have no deciding evidence and the missing records are not in the data. A model "breaking" a tie is a guess. | +seconds to minutes per call | ≈$0.02 per tie on Sonnet 5.5 (estimate: 64 ties × ~1k tokens) up to ~$1 per run on Opus | Non-deterministic (no sampling control on 5.5 models); needs a cache to reproduce | ~3+ days | High; violates "the model never decides state, identity or citations" |
| **E. Hybrid:** deterministic core + a model only as a validated, cache-pinned **cross-check** of screenshot facts (never a decider) | Same or better: catches OCR misreads; facts are accepted only when the two extractors agree or the closed-world check passes | 0 at run time (one-time, offline) | One-time ≈$0.6–1.5 (11 images, Opus 5.5; estimate from the LLM API report), then $0 per run | Run stays deterministic: reads the pinned cache | ~1 day | Low, if written to a separate cache and diffed |

**Recommendation: B now, E optionally, and keep the final run at 0 model calls.**

Rejected alternatives:

- **C** loses at a 2 s runtime. Revisit only if the data grows 10×, *after* B. The algorithmic fix outranks concurrency.
- **D** would buy nondeterminism and policy risk to "fix" cases that, by construction, have no evidence to decide them.

## 4. Parallel versus sequential map

| Stage | Classification | Determinism guard if parallelized |
|---|---|---|
| Evidence parsing per manifest file (`load_evidence` loop) | **Parallel-safe** (pure function per file) | Merge results in sorted `file_id` order. Collect errors per file. No shared store mutation inside workers. |
| Activity loading, identity graph, rules | **Sequential** (single files; global indexes) | — |
| Building observation and identifier indexes (new in B) | **Sequential** (global) | Deterministic insertion order |
| Per-case `link_resources` (memoized) | Parallel-safe (read-only store) | Order-independent results (sets); memo keyed by `(user_id, audit_at)` |
| `assign_workflow_resources` (greedy one-to-one match) | **Must stay sequential** (global matching over all cases) | — |
| Per-case `audit()` | **Parallel-safe after attribution** | Per-case trail buffers, merged in `case_key` order. `flags` copied, never shared. |
| Output sort, `validate_rows`, CSV write, ledger | **Sequential** | `output.csv` sha256 must equal the baseline |

## 5. Migration plan (small, reversible; ordered by impact per unit of risk)

Every step has the same hard gate:

- 59/59 tests and 6/6 custom cases pass.
- Sample metrics are exactly 1.000 / 0.971 / 1.000 / 0.688.
- The eval `output.csv` sha256 stays `7a9683fd…ea50` (unless a step is declared to change behavior).
- Two runs give identical output.

**Rollback trigger for every step:** any metric drop or any unexpected hash change.

| # | Step | Files | Expected change | Tests to add | Status |
|---|---|---|---|---|---|
| 1 | **Index the linker.** Build `{email → obs}`, `{hash → obs}` and `{user_id → obs}` once in `Auditor.__init__`. `link_resources` takes the candidate observations from the index instead of scanning and sorting all 3,050. Keep the visible-first tie order by sorting only the candidates. | `linker.py`, `pipeline.py` | Same hash; ≈0.5 s saved; per-case cost O(matches) | Equivalence test: indexed and full-scan `link_resources` give equal results for all 550 cases | Proposed; awaiting approval |
| 2 | **Memoize links per case.** Compute `link_resources` once per `(user_id, audit_at)` and reuse it in `audit()`. Precompute each case's evidence-file set for `cooccurrence`. | `pipeline.py` | Same hash; another ≈0.4 s saved | Assert the attribution trail is unchanged | Proposed |
| 3 | **Fail loudly on parse errors.** Print the `store.errors` count in the run line, and make it non-zero-exit behind `--strict` (default off, to keep current behavior). | `main.py` | Same hash; visible failure | Test: a corrupted fixture file shows up in the error count | Proposed |
| 4 | **Stamp the configuration.** Print and log the effective `STATE_MAX_AGE_DAYS`, the model IDs and whether the LLM is enabled. Write them into the `llm_usage.json` entry. | `main.py`, `llm.py` | Same hash | Test: the run line contains the config | Proposed |
| 5 | **Per-step provenance and confidence.** Add a `basis` tag (`evidence` / `workflow_attribution` / `time_only_tie`) to the trail's `decision` event for each step. It is *not* added to `output.csv`, so the contract is untouched. | `pipeline.py`, `planner.py` | Same hash; reviewable risk | Snapshot test of the bases for 3 sample cases | Proposed |
| 6 | **Component snapshot baseline.** Golden JSON of linked sets and attribution picks per sample case; the test fails on any diff. | `code/tests/` (new file) | No behavior change | It is the test | Proposed |
| 7 | **Hold-out discipline.** Freeze 8 of the 32 samples as untouched hold-out for any future tuning, and report both splits. | `code/evaluation/main.py` | Honest generalization number | — | Proposed |
| 8 | **Safe vision cross-check (option E).** Add an `--out` flag to `extract_images.py` (default stays `image_facts.json`). Route model records through the same closed-world validation as the OCR path. Diff per record against the OCR cache, and adopt only facts that agree or pass validation. | `tools/extract_images.py`, `screen_ocr.py` (reuse the validator) | Same hash unless the diff finds a real OCR error | Test: vision records with unknown identifiers are rejected | Proposed; billable run needs separate approval |
| 9 | **Pin the SDK major version** (`anthropic>=2,<3`) and set the intent model default to `claude-sonnet-5-5`. Sonnet has server-side fallback; Haiku 5.5 does not. | `requirements.txt`, `config.py` | Same hash (0 calls) | — | Proposed |
| 10 | *(Only if data grows 10×)* **Parallel per-file parsing and per-case audit** with ordered merge and per-case trail buffers | `parsers/__init__.py`, `main.py` | Same hash; useful only above ~10k observations | Hash equality across 1 and N workers | Deferred |

### Cost-cutting summary

The run already costs **$0** and should stay that way. The measures that keep it there:

- Keep model calls out of the scoring path. Rules decided 518/518 intents.
- Pin all model output in disk caches (`intent_cache.json`, `image_facts.json`) so re-runs cost nothing.
- If the vision cross-check (step 8) runs, run it once and offline, on a separate cache.
- Use Sonnet 5.5 rather than Opus for the intent fallback. Prompt caching and the Batch API add nothing at ~31 calls, and Batch is incompatible with the wrapper's `fallbacks` parameter.

The compute cost reductions are steps 1–2: about half the runtime, and linear rather than quadratic growth.

## 6–8. Recovery delegation, validation and adoption

**Not run this session.** No delegation trigger fired:

- tests pass
- custom cases pass
- 0 validation problems
- no sample regression against the previous report

Every proposed step is either output-identical by design (steps 1–7, 9) or needs a separate billable-run approval (step 8).

Per the standing instruction to wait for approval, the next action, on approval, is:

1. `python .claude/tools/recovery_sandbox.py create --id 20261025-linker-index`
2. Brief `failure-recovery` with steps 1–2 under a hard requirement of an identical output hash.
3. Have `change-validator` validate the result.
4. Adopt it only after the user approves.

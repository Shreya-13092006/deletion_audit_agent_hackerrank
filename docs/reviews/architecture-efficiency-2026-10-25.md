# Architecture Efficiency Review, 2026-10-25

Scope: how efficient the current architecture is, measured on this machine (Windows, CPython). All runs wrote to temporary files; root `output.csv` was not touched. The earlier `architecture-2026-10-25.md` is unchanged.

## 1. Measured baseline

| Check | Result |
|---|---|
| Unit tests | **187 OK** in 9.5 s (15.9 s under subprocess timing) |
| Samples (engine and agent) | status 1.000 · step F1 0.971 · evidence 1.000 · sequence 0.688 (22/32) |
| Custom cases | 6/6 (engine), C7–C9 (agent) |
| Agent output on 518 | sha256 `bf634e2c…0e37`, the same as the submitted root `output.csv`; 0 fallbacks, 0 parity diffs, 0 unsupported claims |
| Engine output on 518 | sha256 `1bbba042…b095` |
| Independent verifier | submitted output: 0 FAIL / 1 WARN (case_34 category conflict); gold samples: 0 / 0 |
| Model calls / cost | 0 / $0.00 |

**Changes made outside this session since the last report:**
- `code/audit/intent.py`: negated-deletion handling and a clause-scoped marketing opt-out.
- `code/tests/test_proposed_cases.py`.
- Two new review flags: `OMISSION_SCOPE_REVIEW` (33 cases) and `RECORD_CATEGORY_CONFLICT` (case_34). The review queue went from 112 to **129**.

Outputs and sample metrics are unchanged.

## 2. Stage timings (warm process; `perf2.py`, cProfile)

| Stage | Time | Notes |
|---|---|---|
| Imports | 0.05 s | |
| Parse 94 evidence files (cold) | 0.24 s | only when the evidence-card cache is invalid |
| Evidence cards: build + write / load warm | 0.17 s / 0.06 s | fingerprinted cache |
| `Auditor` init | 0.007 s | |
| Global workflow attribution (550 cases) | 0.068 s | 1,100 cases: 0.121 s, so about linear |
| Engine per-case loop (518) | 0.115 s | about 0.22 ms per case |
| Agent loop + gates (518) | 0.80 s (1.38 s under the profiler) | about 7× the engine; see §3 |
| Verifier (518) | 0.35 s | standard library, independent |
| End-to-end `agent_main.py` | about 1.5 s | |

**Thread-pool experiment:** the engine per-case loop with 4 threads took 0.154 s, *slower* than 0.115 s sequential. Python's global interpreter lock stops threads running this pure-Python work in parallel. The output was identical, but threads give no speed-up here.

## 3. Bottlenecks (profiled)

| # | Where | Evidence | Fix cost |
|---|---|---|---|
| B1 | `code/audit/validate.py:15`: `activity_time = {r["activity_id"]: … for r in activity.rows}` is rebuilt on **every** call | 1,036 calls (gates G1/G2 call it twice per case): **0.40 s of the agent's 1.38 s (about 30%)** | low: compute once per activity index; behavior-neutral |
| B2 | `agent/gates.py:215` `engine_answer`: the G8 parity check re-runs the engine for every case | 0.27 s (about 20%) | none needed: this is the safety design (parity fallback). Could be cached when the agent's decision object *is* the engine's |
| B3 | `intent.classify` runs twice per case (agent + G8) | 1,036 calls, 0.16 s | low: memoize per case text; the new negation/clause logic made it costlier |
| B4 | `state.resolve` / `horizon_start` | 5,667 / 10,345 calls, about 0.19 s | low: cache the horizon string per `audit_at` |
| B5 | Developer loop: the unit tests take 9.5–16 s, against 1.5 s for the product | several test classes re-run the orchestrator over all 550 cases (`LoopTests`, `RealOmissionPolicyTests`, ownership sweeps) | low: share one cached sweep across test modules |

**No accuracy bottleneck is a performance issue.** The 10 imperfect samples are design and data limits: 3 IDs cannot be found in any participant file and 7 are ties (`evaluation_report.md` §2, §9).

## 4. Alternatives compared

| Option | Accuracy | Latency | Cost/run | Reliability / determinism | Effort | Risk to working behavior |
|---|---|---|---|---|---|---|
| **Current: deterministic sequential engine + bounded agent with gates** | samples 1.000 / 0.971 / 0.688 (measured) | 1.5 s end to end (measured) | $0 | byte-identical across runs (measured) | n/a | none |
| Parallel workers: threads | identical (measured) | **slower**: 0.154 s vs 0.115 s for the per-case loop (measured) | $0 | identical hash (measured) | low | low, but no benefit |
| Parallel workers: processes | identical (estimate) | slower at this size (estimate): each worker must rebuild the card store (about 0.07 s) plus process start-up (about 0.1–0.2 s on Windows) to save ≤ 0.8 s of agent work | $0 | needs a stable merge order | medium | low |
| Specialized LLM agents (intent, extraction, tie adjudication) | no measured gain: the remaining misses have no deciding evidence, so a model would be guessing (estimate) | + network latency per call (estimate) | intent ≤ 20 calls, < $0.01; the earlier Gemini planner run made 45 calls (usage_report) | non-deterministic; must stay subordinate to the evidence (AGENTS §6.6) | medium | medium |
| Hybrid: deterministic core + model only for named ambiguous decisions (current opt-in design) | the same as now when off; can't fix ties without evidence | 0 extra when off | $0 off; < $0.01 per run on | gates + validated JSON + rule fallback | done | none |

**Recommendation:** keep the current architecture. It is the fastest option measured, deterministic, costs nothing to run, and none of the alternatives can improve accuracy, because the remaining errors are data limits. The efficiency work worth doing is B1 (and optionally B3–B5): behavior-neutral changes that should cut the agent loop by about 30–50% and the test loop substantially. Concurrency is rejected: the full run is 1.5 s, and threads were measured slower.

## 5. Parallel versus sequential map

| Stage | Classification | Determinism guard if parallelized |
|---|---|---|
| Evidence parsing per file | parallel-safe | merge observations in manifest (`file_id`) order; identical card fingerprint |
| Identity graph load | sequential (global) | n/a |
| Global workflow attribution (one-to-one matching) | **must stay sequential** | n/a |
| Per-case engine audit / agent loop | parallel-safe after attribution (no shared mutable state except the trail) | per-case trail buffers merged in case order; identical `output.csv` sha256 |
| Gates (G1–G11) | parallel-safe per case | the same as above |
| Output sort, contract validation, CSV write | sequential | n/a |

## 6. Migration plan (behavior-neutral; ordered by benefit per unit of risk)

| Step | Files | Expected change | Tests | Rollback trigger |
|---|---|---|---|---|
| 1. ✅ **Executed and adopted 2026-10-25** (`recovery-2026-10-25.md`; agent 1.5 s → 1.0 s, output identical). Compute `activity_time` once per `ActivityIndex` (B1) | `code/audit/validate.py` | agent loop about 0.8 → 0.5 s; output identical | existing contract tests + a hash-equality check | any change to the `output.csv` sha256 or a validation result |
| 2. Memoize `classify` per (text, activity flag) and `horizon_start` per `audit_at` (B3, B4) | `code/audit/intent.py`, `code/audit/state.py` | a further ≈ 0.1–0.2 s | the existing intent/state tests | the same |
| 3. Share one cached 550-case sweep across the test modules (B5) | `code/tests/agent_fixtures.py` + the sweep tests | tests about 9.5 s → about 5 s (estimate) | the suite itself | any test count or result change |
| 4. (optional) Skip the G8 engine re-run when the agent's steps came from the same engine call (B2) | `code/audit/agent/gates.py` | about −0.27 s | parity tests | any parity or fallback change |

**Executed through the subagent:** step 1 (sandbox `20261025-validate-speedup`: recovery, then validator APPROVE, then user approval, then adoption). Steps 2–4 remain optional.

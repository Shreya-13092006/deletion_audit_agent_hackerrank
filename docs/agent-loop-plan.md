# ADR-002: Bounded, gap-driven agentic audit loop on top of the deterministic engine

**Status:** Accepted and implemented on 2026-10-25. See §17 for what changed from the plan.
**Date:** 2026-10-25
**Deciders:** Praneeth (owner)
**Inputs:** the agentic-loop brief (2026-10-25), `docs/dataset-observations.md`, `docs/master-prompt.md`, `docs/reviews/architecture-2026-10-25.md`, `problem_statement.md`, and the current code in `code/audit/`

**Decisions you made on 2026-10-25:**
1. **Entry point:** a new `code/agent_main.py`. Starter files stay untouched.
2. **JSON store:** **both**. A global indexed evidence-card store, plus one JSON case card per case.
3. **Planner:** deterministic by default (final run: 0 model calls, same output hash). Gemini is opt-in and demoed on the 32 samples.

---

## 0. Baseline measured before planning (2026-10-25, this session)

| Check | Result |
|---|---|
| Sample eval (32) | status **1.000** · step P/R/F1 **0.995 / 0.948 / 0.971** · evidence **1.000** · sequence **0.688** |
| Custom cases | **6/6 pass** |
| Root `output.csv` sha256 | `7a9683fd5215f5693e906d0af105a16430df90e621686a26be15b16755e3ea50` |
| Unit tests (Linux VM, Python 3.10) | 65 run; the 2 errors are only `pydantic` missing in the VM. The Windows Python 3.11 run must be repeated at implementation time. |
| Model calls in the final run | 0. All 518 intents were decided by rule. |

**Remaining sample misses** (from architecture-2026-10-25 §2.1; all are design limits):
- case_03/21/25/26/27/28: identity-less analytics ties
- case_04/18/20: records absent from all participant data
- case_23: account chosen by time alone

**An agent loop will not fix these.** No evidence decides them, and a model "deciding" would be a guess. The loop's value is elsewhere: explicit gap-driven investigation, auditable tool use, contradiction surfacing, measurable tool effectiveness, and a hard parity gate against the proven engine.

## 1. Context

The current system (ADR-001, implicit in `docs/master-prompt.md` §7) is a **deterministic sequential pipeline**:
parse → identity graph → link → intent → global workflow attribution → state at `audit_at` → policy → planner → validate.

It is accurate, byte-reproducible and costs $0. An earlier turn's audit (log.txt, 2026-10-24T21:35Z) confirmed:
- It has **no product-level agent loop or tool calling**. The agent loops are Claude Code subagents only.
- Gemini is wired up but has never made a real call.
- A missing key or unavailable model is not logged.
- The Anthropic path has no try/except.

The brief asks for a genuinely agentic but bounded loop: plan, act, observe, replan, stop, gate. It must preserve the 518-row contract, the deterministic fallback and the current baseline.

**Evidence cards today.** `Observation` (`schema.py`) is the evidence card, but it lives only in memory. All 94 files are re-parsed on every run (≈0.42 s). Nothing structured is persisted per case, except trail events in `audit_trail.jsonl`. **The "one JSON card for fast access" feature does not exist yet.** This plan adds it (§6).

## 2. Decision

Add a **bounded orchestrator** (`code/audit/agent/`) that keeps a per-case `CaseState`.

**The agent decides what to investigate next. Deterministic tools decide what is true. Deterministic gates decide what may be written.**

- **Tools** are thin read-only wrappers over existing, tested modules (`identity`, `linker`, `state`, `policy`, `planner`), so there is no second implementation of the logic.
- **The planner** chooses the next tool from the case's *open gaps*. The default `RulePlanner` is deterministic; `GeminiPlanner` is optional and may only choose among the tools allowed for the current gaps.
- **The final decision** is always `policy.evaluate` + `planner.plan` over the `ResourceState`s the tools established. It is then checked by the gates and by a **parity gate** against the existing `Auditor.audit()`.
- **Fallback:** an exhausted budget, a planner error or a gate failure falls back to the existing `Auditor.audit()` decision for that case, flagged as such. `output.csv` therefore can never be worse than today's.

## 3. Options considered

### Option A: keep the pipeline only (status quo)
| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | $0 |
| Accuracy | 0.971 F1 (measured) |
| Brief compliance | **Fails.** No plan, act, observe or replan loop, and no tool contracts, stop conditions or tool-use metrics |

**Pros:** proven and simple. **Cons:** doesn't meet the brief; weak "AI agent" story for judging and the interview.

### Option B: LLM-driven ReAct agent (the model reads evidence and writes steps)
| Dimension | Assessment |
|---|---|
| Complexity | High |
| Cost | ≈518 × 8 calls × ~3k tokens, about $3–10 per run on Gemini Flash (estimate) |
| Accuracy | Lower expected: hallucinated identifiers, wrong citations, non-reproducible |
| Brief compliance | Violates "deterministic tools remain responsible for … final validation" |

**Rejected.** It buys nondeterminism and policy risk for cases that have no deciding evidence.

### Option C (chosen): bounded gap-driven orchestrator, deterministic tools, optional Gemini planner, deterministic gates, parity fallback
| Dimension | Assessment |
|---|---|
| Complexity | Medium (≈900–1,100 new lines incl. tests; additive) |
| Cost | $0 by default. Gemini demo on 32 samples ≈ $0.05–0.10 (§11) |
| Accuracy | Equal to baseline by construction (parity gate); never lower |
| Brief compliance | Full: loop, tools, replanning, stop conditions, gates, logging, metrics |

**Pros:** meets the brief, keeps every proven property, and is honest about what the model does.
**Cons:** two code paths (agent + engine), which the parity gate keeps in lockstep. Gemini changes only the *order and efficiency* of investigation, not answers.

## 4. Trade-off analysis

The core tension is **agency vs. correctness**. In this dataset, correctness comes from exact joins and time rules that the engine already gets right. Giving a model authority over identity, state or citations can only lower the score.

So agency is placed where it is safe and visible:
- **choosing which gap to investigate next**
- **deciding when the evidence is sufficient**
- **surfacing contradictions for review**

The cost is a second code path. We accept it because tools reuse engine functions, and parity is a hard gate in tests and at run time.

## 5. Architecture

```
agent_main.py ──► EvidenceCardStore.load_or_build()      (cache/evidence_cards.json, fingerprinted)
                  IdentityGraph, rules, global workflow attribution (unchanged, run once)
                         │
             for each case (sorted by case_key)
                         ▼
   ┌──────────────── Orchestrator.run(case) ─────────────────┐
   │ CaseState ← init(case)   open_gaps ← {INTENT}             │
   │ loop (≤ MAX_ITER, ≤ MAX_TOOL_CALLS):                       │
   │   1. plan    planner.next(state) → ToolCall | STOP         │
   │              (Rule default; Gemini opt-in, validated)      │
   │   2. act     registry[tool].run(state, args)  (read-only)  │
   │   3. observe merge facts, provenance, contradictions       │
   │   4. replan  recompute open_gaps from state                │
   │   5. stop?   sufficient | no useful tool | budget | N/A    │
   │ decide  policy.evaluate + planner.plan over resolved states│
   └─────────────────────────────┬─────────────────────────────┘
                                 ▼
          Safety & verification gates G1–G8 (deterministic)
                 │ pass                         │ fail / budget exhausted
                 ▼                              ▼
          agent decision                 Auditor.audit(case) fallback + flag
                 └──────────────┬───────────────┘
                                ▼
       CaseCard → cache/case_cards[_sample].json · trail → audit_trail_agent*.jsonl
       validate_rows → output.csv (same schema) · usage ledger (agent_* labels)
```

### 5.1 Per-case state schema (`audit/agent/state.py`, persisted as the case card)

```jsonc
{
  "case_id": "case_12", "audit_at": "...", "reported_status": "...",       // inputs (request_text kept only as sha256 + language guess)
  "intent": {"authorized": true, "reason": "rule:deletion", "flags": []},
  "identity": {"user_id": "user_12", "status": "RESOLVED|UNRESOLVED|AMBIGUOUS",
               "emails": [...], "hashes": [...], "phones": [...],         // canonical, provenance per identifier
               "provenance": [{"identifier": "...", "source": "user_audit_log", "ref": "audit_41"}]},
  "resources": {                                                          // one entry per linked resource
    "analytics_9914": {"system_id": "...", "record_type": "...", "link": {"reason": "identifier|resource_link:x|repopulates:y|workflow_attribution", "evidence_id": "..."},
                       "state": "PRESENT|ABSENT|ACTIVE|DISABLED|BLOCKED|UNKNOWN", "pii": true, "state_evidence": "evidence_01",
                       "timeline": [{"at": "...", "state": "...", "evidence_id": "...", "replica": "..."}],
                       "checks": ["timeline", "replicas", "retention"], "treatment": {...}}},
  "gaps": {"open": ["STATE_UNKNOWN:account_9797"], "closed": [{"gap": "...", "by": "tool", "iter": 3}]},
  "contradictions": [{"resource_id": "...", "kind": "found_then_not_found|primary_vs_replica|claim_vs_evidence|status_vs_findings", "evidence": [...], "resolution": "latest_valid|any_replica_present|evidence_over_claim|unresolved"}],
  "tool_calls": [{"iter": 1, "tool": "resolve_identity", "args": {}, "planner": "rule|gemini", "new_facts": 3, "closed_gaps": ["IDENTITY"], "ms": 1.2}],
  "budget": {"iterations": 7, "tool_calls": 7, "model_calls": 0, "exhausted": false},
  "decision": {"status": "INCOMPLETE", "steps": [...], "source": "agent|fallback", "parity": "match|diff"},
  "gates": {"G1": "pass", ...}, "flags": [...], "review": {"required": false, "reasons": []}
}
```

### 5.2 Gap catalogue (what the planner reasons over)

| Gap | Opened when | Closed by |
|---|---|---|
| `INTENT` | always first | `classify_intent` |
| `IDENTITY` | intent authorized | `resolve_identity` |
| `DISCOVERY` | identity known (or ad hoc) | `search_evidence` |
| `LINKS` | new resources found | `follow_links`: repeat until no new resources (trace_id, `source_resource_id`, recreation) |
| `ACCOUNT` | no `account_*` linked | `attribute_workflow`: reads the precomputed global attribution; heuristic, flagged |
| `STATE:<rid>` | resource has no resolved state | `reconstruct_timeline` |
| `REPLICA:<rid>` | resource seen in a replica-pair or failover source, or a contradiction | `check_replicas` |
| `FLOW:<rid>` | DATA_FLOW resource or recreation link | `check_sync_paths` |
| `RESTORE:<rid>` | BACKUP_ARCHIVE resource | `check_backup_restore` |
| `RETENTION:<rid>` | SECURITY_AUDIT_LOG / LEGAL_HOLD_RECORD / ACCOUNT_TOMBSTONE, or REDACT/ANONYMIZE types | `check_retention_pii` |
| `VERIFY` | all other gaps closed or unclosable | `verify_plan` (runs the gates; it never invents steps) |

A gap that its tool ran on but could not close (e.g. no visible evidence) becomes **unclosable**. It keeps its existing fail-safe flag (`STATE_UNKNOWN`, `NO_CITABLE_PROOF_AT_AUDIT`, …) and is never retried.

## 6. The JSON cards ("everything in one card for fast access")

**6.1 Global evidence-card store: `code/cache/evidence_cards.json`**
- `meta`:
  - `fingerprint` = sha256 over (each manifest file's bytes, `system_activity.csv`, `image_facts.json`, the parser source files)
  - `schema_version`
  - counts
  - no wall-clock fields, so the file is deterministic
- `cards`: every `Observation` as a JSON object. Sets become sorted lists; `attrs` are kept.
- `index`: `resource → [card idx]`, `email → [...]`, `hash → [...]`, `user → [...]`, `system → [...]`, `evidence_id → [...]`
- `covers` (snapshot_scope), `links` (source_resource_id), and an activity digest (recreation links, non-deletion resources, account deletes)
- **load_or_build:** load when the fingerprint matches; otherwise re-parse and rewrite. A corrupt or partial file is discarded and rebuilt (fail-safe).
- **Equivalence test:** the cards rehydrated from JSON are field-for-field equal to fresh parser output for all ≈3,050 observations.

**6.2 Per-case cards: `code/cache/case_cards.json` (eval) and `case_cards_sample.json`**
- One object keyed by `case_id`, containing the §5.1 schema.
- One file, so a reviewer or the interview demo can open any case instantly.
- A review queue is derived from it: cases with `review.required`.
- PII handling: identifiers are already in the participant dataset (fictional). `request_text` is stored only as a hash.

## 7. Tool contracts (`audit/agent/tools.py`)

Every tool:
- is pure and **read-only** (capability `read_evidence`; the registry refuses any tool needing `execute_remediation`)
- has typed args/returns (dataclasses + a JSON schema exported for the Gemini planner)
- is idempotent
- returns `ToolResult{new_facts:int, closed_gaps:[], opened_gaps:[], contradictions:[], notes:[], cost:{}}`

| Tool | Preconditions | Wraps (existing) | Effect on state |
|---|---|---|---|
| `classify_intent` | gap `INTENT` | `intent.classify` + CLASSIFY_REQUEST activity | sets `intent`. Not authorized → `STOP(NOT_APPLICABLE)` |
| `resolve_identity` | `IDENTITY` | `IdentityGraph.resolve_email` + the audit log (old emails, `field_name=email_hash`), sha256 check of stored vs computed hash | sets `identity` + provenance. Ambiguous → ad-hoc identity + flag (never guesses) |
| `search_evidence` | `DISCOVERY` | the card-store index (email / hash / user_id), `linker.matches` (decoy rule), `visible` | adds resources with link reason `identifier` / `identifier_later_evidence` |
| `follow_links` | `LINKS` | `store.links`, `activity.recreation_links`, `_no_conflict` | adds resources linked through `source_resource_id` and repopulation paths |
| `attribute_workflow` | `ACCOUNT` | `Auditor.workflow_resources` / `ambiguous_accounts` (global, precomputed) | adds an attributed account; flags `ACCOUNT_FROM_WORKFLOW_ACTIVITY` / `…TIME_ONLY_TIE` |
| `reconstruct_timeline` | `STATE:<rid>` | `state.resolve` (audit_at cutoff, 14-day horizon, snapshot_scope omission) | sets state, pii and evidence; records the timeline |
| `check_replicas` | `REPLICA:<rid>` | observations grouped by `replica` at the same `observed_at` | records `primary_vs_replica`; confirms the any-copy-present rule |
| `check_sync_paths` | `FLOW:<rid>` | DATA_FLOW observations + recreation links ≤ audit_at | ACTIVE/DISABLED state; opens `STATE` for repopulated downstream records |
| `check_backup_restore` | `RESTORE:<rid>` | `restore_allowed` / BLOCKED facts | ACTIVE (restore risk) / BLOCKED |
| `check_retention_pii` | `RETENTION:<rid>` | **new deterministic condition checks** for rule_12 (`retention_until ≥ audit_at`), rule_13 (hold active / `retained_until ≥ audit_at`) and rule_15 (tombstone keeps only `user_id`); PII flag from `has_direct_identifiers` | confirms retain vs treat; flags `RETENTION_EXPIRED` / `HOLD_INACTIVE` (none today: all dates are 2031–2034) |
| `verify_plan` | `VERIFY` | `policy.evaluate`, `planner.plan`, `validate_rows` checks | runs the gates and produces the decision |

## 8. Planner and replanner (`audit/agent/planner.py`)

**RulePlanner (default, deterministic).**
- Open gaps are kept in a priority queue: INTENT > IDENTITY > DISCOVERY > LINKS > ACCOUNT > STATE > REPLICA > FLOW > RESTORE > RETENTION > VERIFY, then resource_id ascending.
- `next(state)` returns the tool registered for the top gap whose preconditions hold, or `STOP` when no gap is open or closable.
- **Replanning** happens after every tool: gaps are recomputed from the state, so a discovered connector opens `FLOW`, a contradiction opens `REPLICA`, and a repopulated record opens `STATE`.

**GeminiPlanner (opt-in: `--planner gemini`).**
- **Input:** a compact, **PII-scrubbed** state summary: gap names with **opaque resource handles** (`r1, r2…`, never real IDs, emails or hashes), counts, tools already run, and remaining budget.
- **Output:** a `response_format` JSON schema `{tool: enum(allowed_for_open_gaps), target: enum(handles)|null, stop: bool, reason: string≤200}`. It uses `llm.json_call` (provider abstraction, prompt-hash disk cache) with thinking `minimal` on `gemini-3.5-flash-lite`.
- **Validation (G7):**
  - A tool not allowed for an open gap, an unknown handle, invalid JSON, an API error, a missing key or a refusal are logged and replaced by the RulePlanner's choice.
  - `stop=true` while closable gaps remain is overridden.
- **Model authority:** the model chooses the investigation order only, never facts. Each choice is logged with its tokens.

**Contradiction detection** runs after every observe step. It covers found→not-found over time, primary vs replica, activity claim vs evidence (e.g. `DELETE_RECORD SUCCESS` while evidence still shows PRESENT), and `reported_status=COMPLETE` vs findings. Each contradiction is recorded with the existing deterministic resolution rule, or `unresolved` → review queue.

## 9. Stop conditions (all configurable in `config.py`, defaults shown)

1. **Not applicable:** intent not authorized → stop immediately with `[]`.
2. **Sufficient:** no open gaps, i.e. every linked resource has a resolved or unclosable state and `verify_plan` passed.
3. **No useful action:** no open gap has an applicable, unexecuted tool.
4. **Budget:**
   - `AGENT_MAX_ITERATIONS=24` and `AGENT_MAX_TOOL_CALLS=40` per case. These are sized from the sample maximum: 14 steps → ≤14 resources × ~2 checks plus a fixed ~6.
   - Model calls are capped at `AGENT_MAX_MODEL_CALLS_PER_CASE=8` and `AGENT_MAX_MODEL_CALLS_PER_RUN=400`.
5. **Exhaustion → fallback:** flag `AGENT_BUDGET_EXHAUSTED`, use `Auditor.audit(case)`, and mark `decision.source=fallback`.

## 10. Safety and verification gates (`audit/agent/gates.py`)

| Gate | Check | On failure |
|---|---|---|
| G1 contract | `validate.py` rules: keys, numbering, op/phase/state, order, evidence presence/absence | fallback + flag |
| G2 time | every cited evidence id is in the manifest or activity and captured ≤ `audit_at` | fallback + flag |
| G3 claim support (**unsupported-claim rate**) | every FINDING and COMPLETE verification maps to a card fact with matching state/pii on that resource at ≤ audit_at; every step's resource is linked by identifier, link or flagged attribution | fallback + flag; counted in the metric |
| G4 completion | `COMPLETE` ⇒ no finding, every step cited, primary profile verified absent, retained records verified present; otherwise force INCOMPLETE (existing `NO_CITABLE_PROOF` logic) | force INCOMPLETE |
| G5 not-applicable | `NOT_APPLICABLE` ⇒ `[]` | fallback |
| G6 no mutation | registry has no tool with `execute_remediation`; `ApprovalGate` unchanged; remediation steps are *proposals* with empty evidence; nothing claims an operation happened without a citable fact | hard error (test) |
| G7 model output | planner JSON schema, allowed-tool and handle validation, PII scrub before sending | ignore the model output, use the rule choice |
| G8 parity | agent decision == `Auditor.audit(case)` (status + steps) | use the engine decision; flag `AGENT_PARITY_DIFF` → review queue |

**Human review / RBAC.** These go to `review.required` and the derived review queue:
- `ACCOUNT_WORKFLOW_TIME_ONLY_TIE`
- `IDENTITY_AMBIGUOUS`
- `RECORD_SHOWS_OTHER_CONTACT`
- unresolved contradictions
- parity diffs

Roles stay as in `guardrails.ROLES`. The orchestrator gets `planner` + `resolver`; `executor` is never granted.

## 11. Logging, usage and estimated API cost

- **Trail** (`audit_trail_agent[_sample].jsonl`): `agent_iteration`, `tool_call` (tool, args with handles, planner, new_facts, closed_gaps, ms), `contradiction`, `gate`, `fallback`, `stop` (reason), plus the existing `llm_*` events and a **new `llm_unavailable`** event (missing key or SDK).
- **Run line:** effective config (planner, budgets, `STATE_MAX_AGE_DAYS`, models, LLM enabled) and the count of parse errors.
- **Usage ledger:** labels `agent_eval_run` and `agent_sample_gemini`. `usage_report.md` gets a per-model + overall section.

| Scenario | Calls (est.) | Tokens (est.) | Cost (est.) |
|---|---|---|---|
| Final run (RulePlanner) | 0 | 0 | **$0.00** |
| Gemini planner demo, 32 samples | ~6–10 decisions/case → **190–320** | ~600 in + ~60 out each → ~115–190k in, 12–20k out | **≈$0.04–0.11** at $0.30 / $2.50 per M |
| (Not planned) Gemini on all 518 | ~3,100–5,200 | ~1.9–3.1M in | ≈$0.6–1.8 + free-tier rate limits |

Estimates come from the prompt design above. Real numbers will be read from the ledger. **The billable demo needs your separate go-ahead and a `GEMINI_API_KEY` in env.**

## 12. Observation → coverage matrix

Status: ✅ covered in code + test · 🟡 covered but partial / untested at the agent level · ❌ gap. "Agent test" means a new test in `code/tests/test_agent_*.py`.

| # | Observation (brief / dataset-observations) | Current module | Status | Agent tool | Existing test | New test | Metric |
|---|---|---|---|---|---|---|---|
| 1 | Identity aliases `user_id, customer_reference, subject_reference, subject_selector, lookup_key` | `aliases.IDENTITY_FIELDS` | ✅ | search_evidence | `test_alias_fields`, `test_lookup_key_user_reference` | alias-coverage test over the card store | step recall |
| 2 | Email aliases (`requester_email … lookup_value`, message text) | `aliases`, `common.record_observation` | 🟡 `query` is not an identity field (0 zero-hit queries today, so it doesn't affect results) | search_evidence | `test_alias_fields` | add `query`; test zero-hit query links | step recall |
| 3 | trim + lowercase; old/new via audit log | `identity.py` | ✅ | resolve_identity | `test_email_casing…`, `test_old_and_new…` | identity provenance test | status acc |
| 4 | SHA-256 incl. historical, `field_name=email_hash` | `identity.py` | 🟡 stored vs computed hash is not cross-checked | resolve_identity | `test_hash_algorithm…`, `test_audit_log_email_hash…`, `test_case12_hash_trap` | mismatch → flag test | identity acc |
| 5 | Never match on names; decoys | `linker.matches`, `_no_conflict` | ✅ | search_evidence, follow_links | `test_never_link_by_name`, `test_record_naming_other_user…`, `test_decoy_search…case28` | agent-level decoy test | step precision |
| 6 | Canonical evidence cards, persisted | `schema.Observation` (memory only) | ❌ not persisted | EvidenceCardStore | — | build/load equivalence; fingerprint invalidation; corrupt-file rebuild | runtime |
| 7 | file_id ↔ evidence_id; trace_id started→completed | `parsers/logs.py`, `validate.py` | ✅ | search_evidence | `test_started_and_completed…`, `test_no_citation_after_audit` | — | evidence acc |
| 8 | record_type inferred only from tables/rules | `aliases.COLLECTION_RECORD_TYPE`, `state._record_type` | ✅ | reconstruct_timeline | `test_case12_contact_record…` | — | field acc (operation) |
| 9 | audit_record via subject_reference + rule_12 RETAIN | `policy.evaluate` | 🟡 the retention *condition* (`retention_until`) is not checked | check_retention_pii | `test_security_audit_log_is_retained…` | expired retention / inactive hold tests | step F1 |
| 10 | audit_at / observed_at, latest valid, freshness | `state.resolve`, `linker.visible` | ✅ | reconstruct_timeline | `test_audit_cutoff…`, `test_later_reading_wins…`, `test_stale_reading…`, C3, C6 | — | evidence acc |
| 11 | Any replica present ⇒ present | `state.DOMINANCE` | ✅ | check_replicas | `test_replica_drift…`, `test_replica_drift_case16`, C2 | contradiction recorded | step recall |
| 12 | Sync/import/replication recreation | `activity.recreation_links`, linker | ✅ | check_sync_paths, follow_links | `test_recreating_connector…`, `test_recreation_paths`, C4 | — | step F1 |
| 13 | Backups / restore blocking | `policy` BACKUP_ARCHIVE | ✅ | check_backup_restore | `test_recreation_paths`, C4 | — | step F1 |
| 14 | Tombstones (keep user_id only) | `policy` + `common` | ✅ (identifier rule untested at field level) | check_retention_pii | `test_tombstone_cases`, `test_tombstone_keeps_reference…` | field-level test | step F1 |
| 15 | Legal holds | `policy` RETAIN | 🟡 "active" not checked | check_retention_pii | `test_legal_hold_retained` | inactive-hold test | step F1 |
| 16 | Support message REDACT vs attachment DELETE | `policy`, `state.SPECIFIC_TYPES` | ✅ | check_retention_pii | `test_support_message_redacted…` | — | field acc |
| 17 | Workflow attribution only where justified | `Auditor.assign_workflow_resources` | ✅ (flagged) | attribute_workflow | `test_cooccurrence…`, `test_no_second_record…`, `test_time_only_tie_is_flagged` | flagged → review queue test | status acc on flagged subset |
| 18 | snapshot_scope bounds absence | `ScopeCover`, `state.resolve` | ✅ | reconstruct_timeline | `test_snapshot_scope…`, `test_omission_never_overrides…`, `test_cover_captured_after_audit…` | — | step precision |
| 19 | Screenshots: OCR cache, closed-world, 3 readings, pydantic; model vision separate | `screen_ocr.py`, `vision_schema.py`, `tools/extract_images.py` | ✅ | search_evidence (cards) | `test_shipped_cache_validates`, `test_confusion_repair…`, `test_unknown_identifier_needs_two…`, `test_model_backend_cannot_overwrite_ocr_cache` | — | evidence acc |
| 20 | COMPLETE / INCOMPLETE / NOT_APPLICABLE rules; marketing-only trap | `intent.py`, `planner.py`, `validate.py` | ✅ | classify_intent, verify_plan | `test_all_three_classifications`, `test_non_deletion_requests`, C5 | — | status acc |
| 21 | Recommendation ≠ evidence an operation occurred | `planner` (empty evidence on remediation) | ✅ / ❌ claim-vs-evidence not surfaced | contradiction detector, G3 | `test_incomplete_order_and_blank_future_evidence` | claim-vs-evidence contradiction test | unsupported-claim rate |
| 22 | RBAC / approval / no mutation | `guardrails.py` | ✅ | registry + G6 | `test_rbac_denies…`, `test_irreversible…` | registry has no executor tool | — |
| 23 | Gemini optional planner via provider abstraction | `llm.py` (intent only) | ❌ no planner | GeminiPlanner | `test_llm_gemini.py` (fake transport) | planner validation, fallback on bad JSON / API error / refusal / no key | tool-use effectiveness |
| 24 | Missing key / API failure / invalid JSON / exhaustion handled | `llm.py` | 🟡 Anthropic path has no try/except; missing key not logged | — | `test_http_error…`, `test_bad_json…` | `llm_unavailable` event; Anthropic exception path; budget-exhaustion fallback | — |
| 25 | Log tool calls, evidence, decisions, iterations, tokens, cost (no secrets) | `trail.py`, `llm.record_usage` | 🟡 no tool/iteration events | trail events §11 | — | trail schema test; secret-scan test | — |
| 26 | 518-row schema + deterministic fallback | `validate.py`, `main.py` | ✅ | G1, G8 | e2e tests | agent run: 518 rows, hash equality, 2-run determinism | sequence acc |
| 27 | Parse errors surfaced (review §5 step 3) | `parsers/__init__` | ❌ silent | run line + card-store meta | — | corrupted-fixture test | — |
| 28 | Config stamped in run output (review §5 step 4) | — | ❌ | run line + ledger | — | run-line test | — |
| 29 | Hold-out discipline (review §5 step 7) | — | ❌ | `evaluation/agent_eval.py` | — | report both splits (24 tune / 8 hold-out, fixed list) | generalization |

**Previously requested items still open** (from your earlier prompts and the 2026-10-25 review):
- per-step provenance (`basis` tag) → covered by case cards (§5.1 `link.reason`)
- parse-error visibility (#27)
- config stamp (#28)
- hold-out split (#29)
- Anthropic try/except + `llm_unavailable` (#24)
- SDK pin (review step 9) is done (`anthropic>=1.0,<3`). Leave it.
- Linker index and memo (review steps 1–2) are **done** (`linker._identifier_index`, `Auditor.links_for`).

## 13. Minimal file changes

**Never touched** (starter repo): `AGENTS.md`, `CLAUDE.md`, `README.md`, `agent_trace_instructions.md`, `problem_statement.md`, `code/main.py`, `code/evaluation/main.py`, `dataset/**`. The only exception is the mandatory `log.txt` appends (AGENTS.md §2).

| File | Change | Size (est.) | Output-hash impact |
|---|---|---|---|
| `code/agent_main.py` | **new** entry: `--split`, `--out`, `--planner rule\|gemini`, `--no-llm`, `--max-iter`, `--max-tools`; writes output, cards, trail, ledger | ~120 | equal by G8 |
| `code/audit/agent/__init__.py`, `state.py`, `tools.py`, `planner.py`, `loop.py`, `gates.py`, `cards.py` | **new** package (§5–§10) | ~650 | — |
| `code/audit/config.py` | add agent budget constants and planner model / env names (additive) | +15 | none |
| `code/audit/aliases.py` | add `query` to `IDENTITY_FIELDS` | +1 | none (verified: 0 zero-hit queries) — **re-verified by hash gate** |
| `code/audit/policy.py` | rule_12 / rule_13 condition checks (expired → treat as normal category, flag) | +20 | none (all dates 2031–2034) — hash gate |
| `code/audit/identity.py` | stored-vs-computed hash mismatch recorded (flag, no behaviour change) | +6 | none |
| `code/audit/llm.py` | try/except on the Anthropic call; `llm_unavailable` trail event | +12 | none (0 calls) |
| `code/tests/test_agent_cards.py`, `test_agent_loop.py`, `test_agent_gates.py`, `test_agent_planner_gemini.py` | **new** tests (§12, ~30 tests, offline fake transport) | ~400 | — |
| `code/evaluation/agent_eval.py` | **new**: agent vs baseline on the samples; adds unsupported-claim rate, tool-use effectiveness, parity, hold-out split | ~150 | — |
| `code/evaluation/evaluation_report.md`, `usage_report.md` | append an agent section (yours; not starter files) | +60 | — |
| `docs/master-prompt.md` | decision log + architecture §7 update | +10 | — |
| `.gitignore` | ignore `code/cache/case_cards*.json`, `audit_trail_agent*.jsonl` | +2 | — |

The existing `main.py` pipeline keeps working unchanged as the reference engine and the fallback.

## 14. Validation plan (after approval)

1. All unit tests (existing + new) on **your Windows Python 3.11** (pydantic present) and in the Linux VM.
2. Custom cases: `python code/evaluation/main.py --custom` (6/6), plus new agent custom cases C7–C9:
   - **C7:** claim-vs-evidence contradiction (activity says deleted, replica present) → INCOMPLETE, review flag
   - **C8:** expired-retention audit record → treated per category, flag
   - **C9:** budget exhaustion → fallback decision identical to the engine
3. Sample evaluation for both entry points; the metrics must be identical: 1.000 / 0.971 / 1.000 / 0.688.
4. **Two full agent runs**, both sha256 = `7a9683fd…ea50` and equal to each other, with 0 validation problems and 0 parity diffs.
5. `agent_eval.py` comparison table:
   - status accuracy, step F1, evidence accuracy, sequence accuracy
   - unsupported-claim rate (target 0)
   - tool-use effectiveness = calls that closed ≥1 gap or added ≥1 fact ÷ all calls
   - mean tool calls per case, fallbacks, contradictions, review-queue size
6. (Optional, billable; separate approval) Gemini planner on the 32 samples: the same metrics plus calls, tokens and cost from the ledger. Expected: identical answers; effectiveness may differ.

**Rollback trigger:** any metric drop, any hash change, or any parity diff that isn't explained. Then the new files are removed and the 5 small edits reverted (they're listed above). The engine is untouched.

## 15. Consequences

- **Easier:** explaining and auditing every case (the case card); instant evidence lookup; demonstrating real tool use and replanning; safe experiments with model planners.
- **Harder:** two paths to keep in sync, mitigated by G8 and the parity tests.
- **Revisit:**
  - If the hidden-set feedback shows attribution errors, the `ACCOUNT` gap is the place to add evidence-seeking tools.
  - If the data grows 10×, parallelize per-case runs after attribution, as in review §4.

## 16. Action items

1. [ ] **You:** approve or adjust this plan (budgets, gap priorities, the 5 small edits to existing non-starter files).
2. [ ] Implement §13 with tests (no installs, commits, pushes or billable calls).
3. [ ] Run §14 steps 1–5 and report the numbers.
4. [ ] **You:** decide on the Gemini demo (§14.6) and provide the key in the environment if yes.
5. [ ] Update the reports and the master-prompt decision log.

## 17. Implementation notes and deviations from the plan

**How to run:**
- `python code/agent_main.py` (518 cases → `output.csv`)
- `--split sample`
- `--planner gemini` (opt-in)
- `--rebuild-cards`
- `python code/evaluation/agent_eval.py`

**Deviations:**
- **Gap order.** INTENT runs after DISCOVERY and LINKS, not first. `intent_for` corroborates the text with CLASSIFY_REQUEST activity on the subject's *linked* records, exactly as the engine does. NOT_APPLICABLE cases still stop right after `classify_intent`.
- **Two more files changed, as pure refactors** (hash-gated), so tools and engine share one implementation:
  - `linker.py`: `link_resources` = `link_by_identifier` + `propagate_links`
  - `pipeline.py`: an optional `store=` argument, plus `audit()` split into `intent_for` / `attribute` / `resolve_state` / `treat` / `finalize`
- **Batched tools.** One call closes every open gap of a kind (e.g. one `reconstruct_timeline` for all resources). That gives 8.6 calls per case, well under the 24/40 limits.
- **Replica check.** It compares genuine primary/replica/failover tables within the same snapshot file through the card index. Inventory snapshots name each collection as its own table, so they are excluded.
- **Retention conditions** (rule_12 / rule_13) only flag and send cases to review; they never change a treatment. All supplied dates are 2031–2034, so nothing lapses today.
- **Card-store timing (Linux VM).** A full parse takes 1.2 s; a warm load takes about 0.65 s, mostly the content fingerprint. Lookups by resource, identifier or evidence file come from the index.

**Originals for rollback:** `docs/reviews/recovery-artifacts/20261025-agent-loop/backup/` (7 engine files and the old `.gitignore`).

**Windows test run (2026-10-25, user):** `python -m unittest discover -s code/tests -t code/tests` → **109 tests OK**. That is the 94 VM tests plus the 15 pydantic-dependent screenshot and extraction-guard tests. The three printed lines are the expected guard messages: OCR-cache overwrite refused, vision without `--allow-vision` refused, missing `GEMINI_API_KEY` blocked.

**Still to do:** the optional Gemini demo (§14.6).

### 17.x Proof gates and corroboration (2026-10-25, approved follow-up)

- Gates are split into **fallback gates** (G1, G5, G6, G8 → engine answer) and **proof gates** (G2, G3, G4, new G9 → re-checked on the final answer, with COMPLETE → INCOMPLETE fail-safe). Before this, a failed gate fell back to the engine's identical answer, so it could not change anything.
- G3 now checks the claimed state, freshness, other copies and supersession from the evidence cards. G9 accounts for every linked record, flow and backup, plus the primary account.
- New gap `CORROBORATE` and tool `corroborate_evidence`. New contradiction kinds `claim_unverified` and `same_time_{existence,pii}_conflict`, and a genuine `unresolved` resolution.
- Coverage matrix updates: #9/#15 retention conditions remain flag-only (by design). #21 claim-vs-evidence ✅, now including unverified claims. Policy for SECONDARY_IDENTIFIER, CACHE_ENTRY, USER_EXPORT, EMAIL_DELIVERY_LOG and PRODUCT_TELEMETRY is now tested. Phones are tested as provenance-only and never a link key. Conflicting readings are tested to persist as separate cards.
- Measured effect: the engine is unchanged (`7a9683fd…ea50`). The agent downgrades 15 eval cases (`1d9870ad…cfde6`), and no sample changes. See `code/evaluation/evaluation_report.md` §8.

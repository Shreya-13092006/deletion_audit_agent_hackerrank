# Token Usage and Cost Report

## Final full-dataset run (the one that produced `output.csv`)

**Submitted `output.csv`:** produced by the proof-gated agent, `python code/agent_main.py --no-llm`, over the 518 cases on 2026-10-25 (sha256 `bf634e2c…0e37`; two runs, byte-identical; this includes the `retained_order_loaded` parser fix, while the pre-fix output was `1d9870ad…cfde6`). The ledger is `code/cache/llm_usage.json`, label `agent_eval_intent`. It ran the rule planner, so no planner model was used and no planner entry was written.

**Baseline engine:** `python code/main.py` (ledger label `eval_run`) writes the baseline predictions (sha256 `1bbba042…b095`; `7a9683fd…ea50` before the parser fix, kept in the backup) to the same root `output.csv`, so running it replaces the submitted file. It differs from the submitted output only in the 15 cases the proof gates downgrade.

Both commands make 0 model calls, so the table below holds for either.

| Provider | Model | Model calls | Input tokens | Output tokens | Total tokens | Est. cost |
|---|---|---|---|---|---|---|
| Google | gemini-3.5-flash-lite (intent fallback) | 0 | 0 | 0 | 0 | $0.00 |
| **Overall** | — | **0** | **0** | **0** | **0** | **$0.00** |

**Per request:** 0 tokens on average and $0.00 estimated cost. 518 requests were processed.

**Why zero:**
- Every deciding step is deterministic code.
- The intent rules settled all 518 request texts (508 deletion, 10 non-deletion, 0 undetermined), so the model fallback was never reached.
- Screenshot facts are read from the validated cache `code/cache/image_facts.json`.

## Screenshot extraction (one-time, before the final run)

| Backend | Engine | Runs | Model tokens | Cost |
|---|---|---|---|---|
| windows-ocr (used) | Windows.Media.Ocr (en-US), local | 33 OCR passes (11 images × 3 readings) | 0 | $0.00 |
| anthropic (blocked) | claude-opus-5-5 vision | 0 | 0 | $0.00 |

**Why the Anthropic backend didn't run:** neither `ANTHROPIC_API_KEY` nor the `anthropic` package is available in this environment.

**If it is used:** each screenshot (about 1800×1150) costs roughly 1.6k input tokens plus 0.3k prompt, and returns 1–2k output tokens. At $4 input / $20 output per million tokens, that comes to about $0.35–0.55 for all 11, paid once. `claude-haiku-5-5` ($0.10 / $0.50 per million) would cost about $0.01 in total.

## Where models can be used

| Use | Default | Calls in final run |
|---|---|---|
| Screenshot facts | local Windows OCR (pipeline input); `gemini-3.8-flash` cross-check with `--backend gemini --allow-vision` (separate file) | 0 (cache) |
| Ambiguous request intent | `gemini-3.5-flash-lite`, thinking `minimal`, PII-scrubbed, cached | 0 |

**Gemini estimate if the cross-check is run:**
- Screenshots: 11 calls on `gemini-3.8-flash` at about 2,240 image tokens (`ultra_high`) + ~500 prompt tokens, and about 2,000 output tokens, cost about $0.11 at $0.75 / $3.75 per million (promotional until 2026-12-31). Thinking at `medium` adds output-priced tokens.
- Intent: up to 20 calls on `gemini-3.5-flash-lite` cost under $0.01.

**Data policy:** on the Gemini free tier, Google may use inputs to improve its products, and human reviewers may read them. A paid (billing-linked) key avoids that.

**Pricing sources:**
- Gemini: https://ai.google.dev/gemini-api/docs/pricing (read 2026-10-25)
- Claude: the claude-api skill model table (cached 2026-10-06) Prices are in `audit/config.py:MODEL_PRICES`, and costs are computed from the recorded usage multiplied by those prices.

## Agent loop runs (`code/agent_main.py`, 2026-10-25)

| Run (ledger label) | Planner | Intent model calls | Planner model calls | Tokens | Cost |
|---|---|---|---|---|---|
| `agent_eval_intent` (518 cases, produced an `output.csv` identical to the engine's) | rule | 0 | 0 | 0 | $0.00 |
| `agent_sample_intent` (32 cases) | rule | 0 | 0 | 0 | $0.00 |
| **Overall** | — | **0** | **0** | **0** | **$0.00** |

**Optional Gemini planner** (`--planner gemini`, model `gemini-3.5-flash-lite`, thinking `minimal`):
- It is not run; it needs `GEMINI_API_KEY` and your approval.
- The prompt is a PII-free gap summary with opaque handles: about 600 input and 60 output tokens per decision, 6–10 decisions per case.
- **32 samples:** about 190–320 calls, 115–190k input and 12–20k output tokens, roughly **$0.04–0.11**.
- **518 cases:** about $0.6–1.8.
- **Hard caps:** 8 model calls per case and 400 per run (`config.AGENT_MAX_MODEL_CALLS_*`).
- **Recording:** answers are cached in `code/cache/planner_cache.json`, and usage is recorded under `agent_<split>_planner`.

### First Gemini planner run (user's Windows machine, 2026-10-25; ledger `agent_sample_planner`)

`python code/evaluation/agent_eval.py --planner gemini`, 32 samples:

| Model | Calls | Cache hits | Input tokens | Output tokens | Est. cost |
|---|---|---|---|---|---|
| gemini-3.5-flash-lite (planner) | 45 | 212 | 9,397 | 3,004 | **$0.0103** |

That is about 290 tokens and $0.0003 per request. Many cases produce the same opaque gap summary, so 212 of 257 planner prompts were served from `planner_cache.json`.

**Why this run doesn't count as the demo result:**
- 110 valid answers were wrongly rejected (planner placeholder bug, now fixed).
- 11 HTTP errors had no retry (now retried).
- That terminal could not read PDF text (now pinned; see evaluation_report §7).

The rerun reuses the cached answers.

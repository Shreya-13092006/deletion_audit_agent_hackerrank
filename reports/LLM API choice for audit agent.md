# Keep the deterministic run; add Claude only for cross-checking

**You don't need an LLM API for this submission, and the final 518-case run should stay at zero model calls.** The code has only two places that can call a model. One is the intent fallback in `code/audit/intent.py`, which made 0 calls on the final run because the multilingual rules decided all 518 cases. The other is the optional one-time screenshot extractor in `code/tools/extract_images.py`, and its output is already produced locally with Windows OCR. The deterministic pipeline currently scores 1.000 status accuracy, 0.971 step F1, 1.000 evidence accuracy and 0.688 sequence accuracy on the 32 public samples. The remaining misses are records with no supporting evidence and attribution ties, and a model cannot fix those without inventing data. If you want a model, use it to cross-check the 11 screenshots once. The smallest change is no new provider at all: keep the existing Anthropic wrapper and choose the model with `AUDIT_INTENT_MODEL` and `AUDIT_VISION_MODEL`. Leave vision on the default `claude-opus-5-5`, which the docs explicitly place on the high-resolution image tier, at roughly $0.58 for all 11 images before thinking tokens. Set intent to `claude-sonnet-5-5`, which costs cents and, unlike Haiku 5.5, supports server-side fallback ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing); [Vision](https://platform.claude.com/docs/en/build-with-claude/vision); [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)). The only completely free route with vision and schema-enforced JSON is Gemini's free tier. It would need a second provider adapter, its free-tier inputs may be used for training, and its rate limits are not officially published. The extra cost and risk of that route outweigh the roughly $0.60 it saves.

## Two model touchpoints, both with working deterministic fallbacks

The pipeline only consults a model when the deterministic logic cannot decide. In `code/audit/intent.py`, the LLM is consulted only when two things both fail: the multilingual regex rules, and the `CLASSIFY_REQUEST` activity signal. On the final evaluation run the rules decided all 518 requests (508 deletion, 10 non-deletion, 0 undetermined), so the fallback never ran. If it does run and no model is available, it returns a fail-safe `NOT_APPLICABLE` and flags the case. The second touchpoint is `extract_images.py --backend anthropic`. It is opt-in: it refuses to run without `--allow-vision`, and it prints `BLOCKED` when the SDK or `ANTHROPIC_API_KEY` is missing. The default backend is Windows.Media.Ocr. It reads each image at three settings (1x, 2x, and 2x grayscale), parses the text deterministically, and accepts an identifier only if it is already known elsewhere in the data or two OCR readings agree. It produced **26 records from 11 screens and rejected 10 tokens** (all non-customer contacts), cached in `code/cache/image_facts.json`.

`code/audit/llm.py` supports only the Anthropic SDK. It calls `beta.messages.create` with a `json_schema` set in `output_config`, the `server-side-fallback-2026-07-01` beta with `fallbacks="default"`, no sampling parameters, a disk cache keyed by prompt hash, and a usage ledger that feeds `code/evaluation/usage_report.md`. On a `refusal` stop it returns `None`.

Reading `extract_images.py` turned up three things that matter for any vision test:

| Behavior | Consequence |
|---|---|
| The Anthropic path writes back to the same `image_facts.json` that the OCR path produced | Running it with `--force` replaces the OCR facts. There is no output-path flag. |
| That path accepts model records as-is (`rejected=[]`) | It skips the closed-world identifier check the OCR path applies. |
| It records usage to the ledger | A test run would change the usage report unless the ledger is restored afterwards. |

## Five providers, compared on the attributes that matter here

Every provider below can handle about 20 text calls and 11 image calls for under $2. On these volumes, price differences don't decide anything. What does: whether vision and strict JSON are documented to work together, whether the model is stable or preview, and what happens to the data you send.

| Provider | Best fit for A (intent) | Best fit for B (screenshots) | Price per 1M tokens, in/out | Free tier | Strict JSON schema | Data use |
|---|---|---|---|---|---|---|
| Anthropic | `claude-haiku-5-5` / `claude-sonnet-5-5` | `claude-opus-5-5` (high-res tier confirmed) | Haiku $0.10/$0.50, Sonnet $2/$10, Opus $4/$20 | No; "small amount of free credits", amount not stated | GA on all 5.5 models; images are a listed extraction use | No training by default; deleted within 30 days |
| OpenAI | `gpt-6-luna` | `gpt-6-astra` or `gpt-6.1-sol` | Luna $0.10/$0.50, Sol $2/$10, Astra $10/$50 | "Free" tier capped at $100/month; model access and limits not documented | Yes; with images it is implied by the model pages, not stated | No training by default; Responses API stores state unless `store:false` |
| Google Gemini | `gemini-3.5-flash-lite` | `gemini-3.8-flash` | Flash-Lite $0.30/$2.50, 3.8 Flash $0.75/$3.75 (doubles 2027-01-01) | Yes, on stable Flash and Flash-Lite; numeric limits not published | Yes; with images it is implied, not stated | **Free tier used for training, may be human-reviewed** |
| Groq | `openai/gpt-oss-120b` | `qwen/qwen3.8-27b` (**preview**) | $0.15/$0.60; vision $0.80/$4.00 | Likely 30 RPM, 1K RPD, 8K TPM | Strict on gpt-oss and qwen3.8; strict plus images unverified | No retention by default; ZDR available |
| OpenRouter free / Mistral | Free text models / Ministral 3 14B | No verified free vision model / Medium 3.5 | $0 / Mistral prices secondhand only | 50 req/day (OpenRouter) / unpublished (Mistral) | Varies by endpoint / page did not confirm | Free routes may train on inputs |

Sources for the table: Anthropic ([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview); [Pricing](https://platform.claude.com/docs/en/about-claude/pricing); [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs); [Privacy Center](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)). OpenAI ([Models](https://developers.openai.com/api/docs/models); [Pricing](https://developers.openai.com/api/docs/pricing); [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits); [Your data](https://developers.openai.com/api/docs/guides/your-data)). Gemini ([Models](https://ai.google.dev/gemini-api/docs/models); [Pricing](https://ai.google.dev/gemini-api/docs/pricing); [Terms](https://ai.google.dev/gemini-api/terms)). Groq ([Models](https://console.groq.com/docs/models); [Structured outputs](https://console.groq.com/docs/structured-outputs); [Rate limits](https://console.groq.com/docs/rate-limits); [Your data](https://console.groq.com/docs/your-data)). OpenRouter ([Limits](https://openrouter.ai/docs/api/reference/limits)). Mistral ([Models](https://docs.mistral.ai/getting-started/models/models_overview/); [Training opt-out](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training)).

### Facts the official docs leave unconfirmed

Several facts in the table could not be confirmed from official pages:

- **Gemini free-tier limits.** Google's rate-limits page gives no numbers and points to AI Studio instead ([Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)). The only figure found is "20 RPD" for 3.8 Flash, from an unanswered forum post ([Forum](https://discuss.ai.google.dev/t/gemini-3-8-flash-free-tier-20-rpd-is-too-limited-for-practical-evaluation/180609)).
- **Groq's limits table** describes itself as both the free plan and the Developer plan.
- **Mistral prices** come only from aggregator sites.
- **Vision plus strict schema in one request.** No provider explicitly documents a request that combines image input with a strict JSON schema; it is implied by feature lists everywhere. Anthropic comes closest, listing data extraction from images as a structured-outputs use case.
- **OpenAI's GPT-6 Sol and Luna image tokenization** is missing from its vision guide ([Images & Vision](https://developers.openai.com/api/docs/guides/images-vision)).
- **Anthropic's high-resolution tier for Sonnet and Haiku 5.5** is inferred from the rule "Claude 4.7 and later". Only Opus 5.5 is named explicitly ([Vision](https://platform.claude.com/docs/en/build-with-claude/vision)).

No provider publishes OCR or multilingual-classification benchmarks per model, so every accuracy ranking below is a judgment, not a measurement.

## Best model per task: accuracy first, since cost is in cents

**Task A (ambiguous multilingual intent).** On cost alone, Anthropic's Haiku 5.5 and OpenAI's `gpt-6-luna` tie at **$0.10 input / $0.50 output per 1M tokens**. Anthropic describes Haiku as built for "classification, extraction, and routing" ([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview); [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)). In this project, though, the model only runs on cases the rules found too ambiguous. That makes reliability on hard inputs more important than price, and Haiku 5.5 has one specific weakness: it **has no server-side fallback**. A declined request stays declined ([Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)), and `intent.py` would then fail safe to `NOT_APPLICABLE`. That answer is wrong for a genuine deletion request. `claude-sonnet-5-5` supports fallback, and 20 calls cost about **$0.022** on it ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)), so it is the better choice here. Two schema rules apply on Opus and Sonnet 5.5. Do not add a `reasoning` field, because requesting one can trigger a billed `reasoning_extraction` refusal ([Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)). Do not send non-default `temperature`/`top_p` values, which return a 400 error on 5.5 models ([Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)). The project's Python files contain no `reasoning` field and the wrapper sends no sampling parameters, so both rules are already met.

**Task B (screenshots into strict JSON).** The goal is reading small identifiers like `backup_9287` correctly. Whether an image is downscaled matters more than the per-token price, and **Opus 5.5 is the only budget-reasonable model documented to process an 1800x1150 screenshot without resizing**. It costs about **2,730 visual tokens** per image, giving roughly $0.58 for all 11 images before thinking tokens ([Vision](https://platform.claude.com/docs/en/build-with-claude/vision)). Opus cannot turn thinking off, so actual cost could be 2 to 3 times that and still stay under $2. OpenAI's `gpt-6-astra` also processes the image at full size (about 2,463 tokens), but it costs about $1.43 for this task, and OpenAI's guide warns about small text and Japanese/Korean scripts ([Images & Vision](https://developers.openai.com/api/docs/guides/images-vision)). OpenAI also fixed an image-encoding bug that degraded GPT-6 Sol and Luna on September 25, 2026 ([Changelog](https://developers.openai.com/api/docs/changelog)), which argues against trusting those models without re-testing. Gemini 3.8 Flash defaults to 1,120 tokens per image, and Google says higher resolution "rarely improves OCR results for standard documents" ([Media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)). That is efficient, but nobody has tested it on dense, dark-theme tables. Groq's only vision model is a preview model limited to 2,048 tokens per image ([Groq Vision](https://console.groq.com/docs/vision)), and Groq retired four model families during 2026 ([Deprecations](https://console.groq.com/docs/deprecations)). That makes it a poor fit for anything you need to reproduce later.

## An API adds no score and removes no known failure

Both model tasks already work without a model. Intent made 0 fallback calls on all 518 cases. Screenshot facts are cached, validated with pydantic, and checked against identifiers known elsewhere in the data. The sample misses have causes a model cannot address: records that have no supporting evidence, and ties in deciding which user a record belongs to. Inventing records to fill those gaps would break the rule that every finding cites participant-visible evidence. The submission accepts a 0-call usage report.

Adding a model would also cost reproducibility. Anthropic now documents "no determinism control" on 5.5 models ([Migration 2026-10-21](https://platform.claude.com/docs/en/api/migration-2026-10-21)), so a model-dependent `output.csv` would rely on the cache to come out identical between runs.

The case for a model is narrower: it would be an **independent check of the Windows-only OCR**. That OCR is the one part of the pipeline you cannot re-run on macOS or Linux, and nothing else currently checks it. A one-time vision pass that agrees with all 26 OCR records makes the evidence layer more trustworthy, and it does so without touching the final run. That is the whole value case.

The tradeoffs between the options:

| Option | What you gain | What it costs |
|---|---|---|
| Anthropic (no new code) | Fits the existing wrapper | Requires a key and a few dollars; Anthropic has no free tier ([Pricing FAQ](https://platform.claude.com/docs/en/about-claude/pricing)) |
| Gemini free tier | The only $0 route with vision and schema-enforced JSON | A new adapter, and inputs may be used for training and read by human reviewers ([Terms](https://ai.google.dev/gemini-api/terms)) |
| OpenRouter free | $0 for text | No verified free vision model, and it routes to free models at random ([Limits](https://openrouter.ai/docs/api/reference/limits)) |

Training on the inputs is a poor look for a project about data deletion, even though the data is fictional.

## Change one environment variable, then A/B the screenshot cache

The smallest change needs no new code for the intent path. Set `AUDIT_INTENT_MODEL=claude-sonnet-5-5` and leave `AUDIT_VISION_MODEL` at its `claude-opus-5-5` default. The wrapper's request format is supported on all 5.5 models, so only the model string changes ([Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). Two small, file-touching follow-ups need your approval first:

1. **Pin the SDK major version.** `requirements.txt` says `anthropic>=1.0`, which now installs SDK 2.x and API version `2026-10-21` ([Migration 2026-10-21](https://platform.claude.com/docs/en/api/migration-2026-10-21)).
2. **Fix the vision path's write-back.** Before any vision run, either give `extract_images.py` an output-path flag or copy `image_facts.json` and `llm_usage.json` aside first, because the Anthropic path overwrites the OCR cache. Ideally, also route Anthropic records through the same closed-world validation the OCR path uses.

The A/B test, once approved:

1. Back up `code/cache/image_facts.json` and `code/cache/llm_usage.json`.
2. Run `python code/tools/extract_images.py --backend anthropic --allow-vision --force` with the key read from the environment.
3. Move the result to a separate file, for example `image_facts.vision.json`, and restore the OCR cache.
4. Diff the two files record by record on `resource_id`, `email`, `customer_reference` and `result`.
5. Accept a vision fact only if it agrees with OCR, or if it passes the closed-world check (the identifier is known elsewhere in the dataset). Log every disagreement and resolve it by looking at the screenshot, not by trusting either source.
6. If any fact changes, rerun the four evaluation commands:
   - `python -m unittest discover -s code/tests -t code/tests` must stay 59/59.
   - `python code/evaluation/main.py -v` must show no drop from 1.000 status, 0.971 step F1, 1.000 evidence and 0.688 sequence accuracy.
   - `python code/evaluation/main.py --custom` must stay 6/6.
   - `python code/main.py`, run twice, must produce identical `output.csv` sha256 hashes.

If the ledger is not restored, `usage_report.md` must show the vision run's real token counts. If the diff is clean, record it in `evaluation_report.md` as an independent check and leave the final 518-case run at 0 calls.

## Conclusion

The question changed from "which API" to "what would a model be for". On this dataset a model can only be a second opinion on evidence, never the source of a decision. That limits it to a bounded, one-time role, where reproducibility, not accuracy, is what you would pay for. Two gaps carry real risk. First, the Anthropic vision path skips the closed-world validation that makes the OCR path trustworthy. Second, it would silently overwrite the OCR cache and the usage ledger. Fix those before choosing a model.

If you want one more change after the screenshot cross-check, test the fail-safe instead. The intent fallback's `NOT_APPLICABLE` default is safe only while no model is configured. A Haiku refusal would trigger it on a real deletion request. Choosing a model with fallback for that path (Sonnet 5.5) is the one model choice that affects correctness rather than cost. Do not run anything billable until you approve it.

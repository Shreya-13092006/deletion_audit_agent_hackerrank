# Anthropic Claude API for (A) multilingual deletion-intent classification and (B) one-time screenshot extraction, as of late October 2026

All pages below were read on 2026-10-25 from official Anthropic documentation (platform.claude.com, privacy.claude.com). No API calls were made. Where a fact applies to a "model generation" rather than naming a model, that is flagged as an inference.

Project context checked locally (not a web source): `code/audit/llm.py` calls `client.beta.messages.create(model=..., max_tokens=..., betas=["server-side-fallback-2026-07-01"], fallbacks="default", output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}}, messages=[...])`. It passes images as base64 PNG blocks, sends no `temperature`/`top_p`/`top_k`, and returns `None` on `stop_reason == "refusal"`. `code/audit/config.py` defaults both `INTENT_MODEL` and `VISION_MODEL` to `claude-opus-5-5`, overridable via the `AUDIT_INTENT_MODEL`/`AUDIT_VISION_MODEL` env vars. Its price table (`opus 4/20`, `sonnet 2/10`, `haiku 0.10/0.50`) matches the current official prices. `code/requirements.txt` pins `anthropic>=1.0`. The SDK is not installed in the current Python environment.

## Current model IDs and per-million-token prices (input/output, cache, batch)

### Takeaway
The current generation is Haiku 5.5, Sonnet 5.5 and Opus 5.5, with dateless pinned IDs `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`. Fable 5.1 sits above Opus. Base prices per MTok (input/output) are Haiku $0.10/$0.50 for prompts up to 100k tokens, Sonnet $2/$10 and Opus $4/$20. The Batch API takes 50% off. Haiku 5.5 is 20x cheaper than Sonnet 5.5 and 40x cheaper than Opus 5.5 on both input and output.

### Cited Findings
- Current lineup and API IDs: Claude Fable 5.1 `claude-fable-5-1`, Claude Opus 5.5 `claude-opus-5-5`, Claude Sonnet 5.5 `claude-sonnet-5-5`, Claude Haiku 5.5 `claude-haiku-5-5`. "Every Claude model ID is a pinned snapshot, including the dateless IDs used from the 4.6 generation on." — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- Haiku 5.5 is described as being "For high-volume, latency-sensitive tasks such as classification, extraction, and routing". Sonnet 5.5 is "The best combination of speed and intelligence" and Opus 5.5 is "For long-running agentic coding and knowledge work". Comparative latency: Haiku Fastest, Sonnet Fast, Opus Moderate. — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- All four current models have a 1M-token context window, 128K max output (sync), a Jun 2026 reliable knowledge cutoff, and "text and image input, text output, multilingual capabilities, vision, and tool use". — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- Claude Haiku 5.5 was released October 7, 2026, with status "Active (latest)". — [Haiku 5.5 overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
- Price table (USD per MTok: base input / 5m cache write / 1h cache write / cache hit / output) — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing):
  - Opus 5.5: $4 / $5 / $8 / $0.20 / $20
  - Sonnet 5.5: $2 / $2.50 / $4 / $0.10 / $10
  - Haiku 5.5, prompts up to 100,000 tokens: $0.10 / $0.125 / $0.20 / $0.01 / $0.50
  - Haiku 5.5, prompts over 100,000 tokens: $0.50 / $0.625 / $1 / $0.05 / $2.50
  - Fable 5.1, for reference: $10 / $12.50 / $20 / $0.25 / $50
  - Legacy, for reference: Haiku 4.5 $1/$5; Sonnet 4.6 $3/$15; Opus 4.8 $5/$25
- Cache-hit multipliers: "Cache hits and refreshes on Claude Opus 5.5 and Claude Sonnet 5.5 are priced at 0.05x the base input price". All other models use 0.1x, except Fable 5.1 and Mythos 5.1 at 0.025x. — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Batch prices per MTok (input/output): Opus 5.5 $2/$10; Sonnet 5.5 $1/$5; Haiku 5.5 $0.05/$0.25 (up to 100k-token prompts). "The Batch API allows asynchronous processing of large volumes of requests with a 50 percent discount on both input and output tokens." Batch and caching discounts stack. — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Haiku 5.5 is priced by prompt length: "a request whose prompt is over 100,000 tokens pays higher prices". The 1M-context-at-standard-price rule applies to "Claude 4.6 and later models (except Claude Haiku 5.5)". — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- US-only inference (`inference_geo`) costs 1.1x on Claude 4.6+ models. Global routing, the default, uses standard pricing. — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Tokenizer: "Claude 4.7 and later models ... use a newer tokenizer ... This tokenizer produces approximately 30% more tokens for the same text." Haiku 5.5 "uses the same newer tokenizer". — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing); [Haiku 5.5 overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
- Thinking tokens "are billed as output tokens, even when the thinking text isn't returned to you, and they count toward `max_tokens`". — [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)
- Structured outputs add input tokens: "Claude automatically receives an additional system prompt explaining the expected output format." — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Haiku 5.5's minimum cacheable prompt length is 512 tokens. — [Haiku 5.5 overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview)

### Inferences
- Each request in tasks A and B is far below 100k tokens, so Haiku 5.5's lower tier ($0.10/$0.50) applies.
- Prompt caching gives almost nothing here. A ~300-token classification prompt is below Haiku's 512-token cache minimum. Image calls are one-time with distinct images.
- The project's `MODEL_PRICES` table is correct as of 2026-10-25.

### Gaps
- The pricing page did not state the size of the hidden structured-outputs system prompt. Use token counting to measure it.

## Vision: image token formula, estimate for one ~1800x1150 PNG, resizing and limits

### Takeaway
Cost is `ceil(w/28) x ceil(h/28)` visual tokens. Claude 4.7-and-later models use a high-resolution tier capped at a 2,576 px long edge and 4,784 visual tokens. On that tier an 1800x1150 screenshot is not resized and costs about 2,730 input tokens: 65 x 42 patches, plus prompt text.

### Cited Findings
- "Each patch is a 28×28-pixel block of the image ... An image, therefore, costs `⌈width / 28⌉ × ⌈height / 28⌉` visual tokens." — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Resolution tiers: "High-resolution | Claude 4.7 and later models | 2,576 px | 4,784" and "Standard | All other models | 1,568 px | 1,568". "High-resolution support is automatic on the listed models and requires no beta header or client-side opt-in." — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Reference sizes from the docs:
  - 1920x1080: not resized on high-res, 2,691 tokens. Standard tier downsizes it to 1456x819 at 1,560 tokens.
  - 2000x1500: not resized on high-res, 3,888 tokens. — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Oversized images are downscaled while preserving aspect ratio. To get an error instead, set `"oversized_image": "error"` via the image block's `transformations` field. — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Limits:
  - Maximum dimensions are 8000x8000 px.
  - The per-image size limit is 10 MB (base64) on the Claude API.
  - A request can hold up to 600 images (100 on 200k-context models).
  - Above 20 images per request, a stricter per-image dimension limit applies (stay under 2000 px).
  - Request size limit is 32 MB.
  - Supported formats: JPEG, PNG, GIF, WebP. — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Quality guidance:
  - "If the image contains important text, make sure it's legible and not too small."
  - Lossy compression "can make text difficult to read".
  - Placing the image before the text prompt works best.
  - Listed limitations include hallucination on "low-quality, rotated, or very small images" and approximate counting. — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Worked example from the docs: "At Claude Opus 5.5's $4 USD per million (high-resolution tier), the same [1000x1000] image costs about $5.18 USD per thousand". This confirms that Opus 5.5 is on the high-res tier. — [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- Haiku 5.5 input is "Text and images → text". — [Haiku 5.5 overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
- "Anthropic does not use uploaded images to train models", and image uploads "are ephemeral". — [Vision FAQ](https://platform.claude.com/docs/en/build-with-claude/vision)

### Inferences
- The estimate for one 1800x1150 PNG on the high-res tier: ceil(1800/28)=65, ceil(1150/28)=42, giving **2,730 visual tokens**. This is under both caps, so it is not resized. Adding about 300–600 prompt and schema tokens gives roughly 3,000–3,300 input tokens per call. All 11 images together come to about 30,030 image tokens.
- Sonnet 5.5 and Haiku 5.5 are "later than Claude 4.7", so they should also be on the high-res tier. The page names Opus 5.5 explicitly but does not list Sonnet or Haiku by name.
- If Haiku were on the standard tier, the image would be downscaled to about 1,568 px on the long edge (about 1,5xx tokens). That would lower dense-table legibility. Cropping each table region into separate images would avoid this.
- Dark-theme screenshots are not addressed in the docs. Legibility advice (contrast, no lossy compression) applies, so send PNG rather than JPEG.

### Gaps
- No official benchmark of dense-table OCR accuracy per model (Haiku vs Sonnet vs Opus 5.5) was found.
- The high-res tier membership of Sonnet 5.5 and Haiku 5.5 is inferred from "Claude 4.7 and later", not stated per model.

## Structured outputs (JSON schema enforcement) per model, including with images

### Takeaway
Structured outputs via `output_config.format` (`json_schema`) is GA on the Claude API and needs no beta header. It is supported on Haiku 5.5, Sonnet 5.5 and Opus 5.5, among others. Schema limits apply: `additionalProperties:false` is required, and there are no min/max or length constraints and no recursion. The docs list image extraction as a use case. The output is not guaranteed to match the schema on `refusal` or `max_tokens` stops.

### Cited Findings
- GA status: "beta headers are no longer required. The `output_format` parameter is deprecated" (moved to `output_config.format`). — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Supported models include claude-opus-5-5, claude-sonnet-5-5 and claude-haiku-5-5, plus Fable/Mythos 5.x, Opus 4.5–5, Sonnet 4.5–5 and Haiku 4.5. — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Supported schema features:
  - Basic types, plus `enum` (strings, numbers, booleans or nulls only) and `const`
  - `anyOf`, and `allOf` with limits
  - Internal `$ref`/`$defs`
  - `required`
  - `additionalProperties` "must be set to `false` for objects"
  - Some string formats (`date-time`, `email`, `uuid` and others)
  - `minItems` 0 or 1 only
  - A simple regex `pattern` — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Not supported: recursive schemas, `minimum`/`maximum`/`multipleOf`, `minLength`/`maxLength`, array constraints beyond `minItems` 0/1, external `$ref`, and regex lookaround or backreferences. Sending one returns a 400 error. — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Complexity limits: 20 strict tools, 24 optional parameters across schemas, and 16 union-type parameters. A 400 "Schema is too complex for compilation" error is possible, and compilation times out after 180 s. — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- First use of a schema adds grammar-compilation latency. "Compiled grammars are cached for 24 hours from last use." — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Refusal: "You'll receive a 200 status code. You'll be billed for the tokens generated. The output might not match your schema because the refusal message takes precedence". With `max_tokens`: "The output might be incomplete and not match your schema." — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- "Enum casing isn't guaranteed ... Compare case-insensitively." Required properties come first in the output, then optional ones. — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- Requesting a `reasoning`, `thinking` or `trace` field in the JSON can trigger a `reasoning_extraction` refusal on Opus 5.5 and Sonnet 5.5. That refusal category is billed and has no fallback model. — [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback); [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)
- Haiku 5.5 caveat: "With thinking off, the model can skip a tool call it needs when you also request JSON output." This only matters when tools are used. — [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)
- Forced tool use (`tool_choice` any/tool) returns a 400 error on Opus 5.5 and Sonnet 5.5. Use structured outputs or strict tools with `auto` instead. — [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)

### Inferences
- The project's `output_config.format` json_schema call is the officially recommended path on all three 5.5 models. Switching between them changes only the `model` string.
- Schemas for tasks A and B must avoid `minLength`, `maximum` and similar keywords, and must set `additionalProperties:false`. Do not add a "reasoning" field; a short "explanation" or "evidence" field is the documented safe alternative.

### Gaps
- The structured-outputs page gives no image-specific constraints. It says it can "extract data from images or text" but does not document image-specific behaviour.
- The page I read did not state whether Message Batches support `output_config.format`. The truncated portion was not re-read.

## Free tier / free credits and lowest-tier rate limits

### Takeaway
There is no free API tier. New users get "a small amount of free credits", with no amount stated. Brand-new orgs may begin in an unpublished "Evaluation tier" with limits below Start. Start-tier limits for each 5.5 model are 1,000 RPM, 2M ITPM and 400K OTPM, under a $500/month spend cap. Both tasks' volumes are trivially below these limits.

### Cited Findings
- "New users receive a small amount of free credits to test the API. Contact sales ... for information about extended trials for enterprise evaluation." — [Pricing FAQ](https://platform.claude.com/docs/en/about-claude/pricing)
- "New organizations and organizations with limited usage history may start in the Evaluation tier, with limits below the standard limits shown on this page". — [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- Monthly spend caps: Start $500, Build $1,000, Scale $200,000. Reaching the cap returns a 429 `enforced_spend_limit_reached` error with no `retry-after`. — [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- Start tier limits: Opus 5.5, Sonnet 5.5 and Haiku 5.5 each get 1,000 RPM, 2,000,000 ITPM and 400,000 OTPM, as separate buckets. — [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- Start tier limits for the Message Batches API: 1,000 RPM, 200,000 batch requests in queue and 100,000 per batch. — [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- Cached input tokens do not count toward ITPM for current models. — [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)

### Inferences
- About 31 calls in total, at under 4K input tokens each, will not approach any Start-tier limit. Even unknown Evaluation-tier limits are unlikely to bind, but burst concurrency should be kept modest.

### Gaps
- The free-credit dollar amount and the Evaluation-tier numeric limits are not published on the pages read.

## API data retention and training on inputs

### Takeaway
By default, API inputs and outputs are not used for training. They are deleted from the backend within 30 days. Exceptions are Usage Policy flags (up to 2 years), Files API data under customer control, and zero data retention (ZDR) by agreement. Structured outputs is ZDR-eligible, and its schema is cached for up to 24 hours.

### Cited Findings
- "By default, we will not use your inputs or outputs from our commercial products" for training. The Anthropic API counts as a commercial product. The exception is explicit feedback or opt-in. Page dated August 18, 2026. — [Privacy Center: training](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training)
- "we automatically delete inputs and outputs on our backend within 30 days of receipt or generation". Exceptions:
  - Longer retention under the customer's control (Files API)
  - ZDR agreements
  - Usage Policy flags: "We retain inputs and outputs for up to 2 years" (classifier scores up to 7 years)
  - Legal requirements
  - Page last updated July 1, 2026. — [Privacy Center: retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)
- Structured outputs is "Eligible for ZDR" and HIPAA eligible. "The JSON schema itself is temporarily cached for up to 24 hours since last use". PHI must not be placed in schema property names, enums or patterns. — [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- "Anthropic does not use uploaded images to train models." — [Vision FAQ](https://platform.claude.com/docs/en/build-with-claude/vision)

### Inferences
- The dataset is fictional, so sending request texts and screenshots is low risk. The 30-day retention still applies unless the org has ZDR.

### Gaps
- I did not read the Commercial Terms page directly. The training policy is cited from the Privacy Center.

## Reliability notes (refusals, sampling, deprecations, SDK/API version)

### Takeaway
All 5.5 models have safety classifiers that return `stop_reason:"refusal"` with a 200 status, which the project already handles. Opus 5.5 can't turn thinking off. Haiku 5.5 can, at effort `high` or below. Sonnet 5.5's lowest setting is `between_tools`. Haiku 5.5 has no server-side fallback, so `fallbacks:"default"` is accepted but a refusal stays a refusal. `fallbacks` is not allowed in Message Batches. No 5.5 model is deprecated.

### Cited Findings
- "Claude Fable 5.1, Claude Fable 5, Claude Opus 5.5, Claude Opus 5, Claude Sonnet 5.5, and Claude Haiku 5.5 include safety classifiers that can decline a request ... `stop_reason: "refusal"`". Refusal categories are `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`, `general_harms` and null. — [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)
- Billing: a refusal before any output is billed only for the `bio`, `frontier_llm` and `reasoning_extraction` categories. A mid-stream refusal bills input plus the output streamed so far. — [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)
- Server-side fallback (`fallbacks:"default"` + `server-side-fallback-2026-07-01` beta) is in beta on the Claude API. "Claude Haiku 5.5 has no server-side fallback: with `fallbacks: "default"`, a declined request stays declined, and a list of fallback models returns a 400 error." "The `fallbacks` parameter is not supported on the Message Batches API (a batch item that includes it comes back as an errored result)." — [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)
- Thinking controls per model:
  - Opus 5.5 rejects `disabled` and `between_tools` (400).
  - Sonnet 5.5 accepts `between_tools` at effort ≤ high and rejects `disabled`.
  - Haiku 5.5 accepts `disabled` at effort ≤ high.
  - Default effort: Opus `medium`, Sonnet `high`, Haiku `medium`. — [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking); [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- Sampling: on 5.5 models, "non-default `temperature`, `top_p`, or `top_k` values return a 400 error on every request". In API version `2026-10-21` they return a 400 "at any value". A prefilled final assistant turn is rejected on Claude 4.6+. — [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking); [Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- API version `2026-10-21`: "If you use an SDK, your requests use the API version that was current when your SDK's major version was released." For Python, "Upgrade the `anthropic` package to version 2.0.0". The changes include `MessageParam` being split into role-specific types, and `output_config` living on `BetaSystemMessageParam` in typed beta params. — [Migrating to 2026-10-21](https://platform.claude.com/docs/en/api/migration-2026-10-21)
- Deprecation status:
  - Retirement dates for the 5.5 models: Haiku 5.5 not sooner than Oct 7, 2027; Sonnet 5.5 not sooner than Sep 28, 2027; Opus 5.5 not sooner than Sep 22, 2027.
  - `claude-sonnet-4-5-20250929` is deprecated, with retirement on Nov 30, 2026.
  - `claude-haiku-4-5-20251001` is Active, with retirement "Not sooner than October 15, 2026" (that date has already passed).
  - At least 60 days' notice is promised before a retirement. — [Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- Limitation listed in the docs: no determinism control. With sampling parameters gone, outputs are not guaranteed identical across runs. — [Migrating to 2026-10-21](https://platform.claude.com/docs/en/api/migration-2026-10-21)

### Inferences
- Migration effort for the existing wrapper is minimal. Changing `AUDIT_INTENT_MODEL` / `AUDIT_VISION_MODEL` to `claude-haiku-5-5` or `claude-sonnet-5-5` should work as-is: same call shape, `output_config.format` supported, no sampling params sent. Caveats:
  - On Haiku 5.5, `fallbacks:"default"` gives no rescue. The existing `None`-on-refusal path then triggers the deterministic fallback. An optional manual retry on Sonnet could be added.
  - Moving to the Batch API would require removing `fallbacks` and the beta header. For about 31 calls the batch saving is cents, so batching is not worth the added latency or complexity.
  - `effort="low"` (the wrapper default) is valid on all three models. The docs list `xhigh`/`max` as the levels that block disabling thinking, which implies `low` is a valid value. Opus 5.5 will still think adaptively and bill thinking as output.
  - `requirements.txt` `anthropic>=1.0` will now resolve to SDK 2.x (API version 2026-10-21). The wrapper passes plain dicts, so the type-level changes probably do not affect it. Verify with one test call, or pin the major version for reproducibility.
- The wrapper caches results by prompt hash, which already addresses run-to-run nondeterminism.

### Gaps
- No official multilingual accuracy figures for EN/ES/PT/FR/JA/KO per 5.5 model were found. Only "multilingual capabilities" is stated.
- Refusal false-positive rates for privacy or deletion texts are not published. The `general_harms` category is unbilled, so a refusal would not cost money.

## Estimated total cost: ~20 text calls + 11 image calls on Haiku vs Sonnet vs Opus

### Takeaway
At standard (non-batch) prices, the whole job costs about **$0.016 on Haiku 5.5**, **$0.31 on Sonnet 5.5** and **$0.63 on Opus 5.5**. The 22,000 image-output tokens make up over 70% of the total on every model. All three are negligible in absolute terms.

### Cited Findings
- Prices and formula used: Haiku $0.10/$0.50, Sonnet $2/$10, Opus $4/$20 per MTok. Batch takes 50% off. Image cost is ceil(w/28) x ceil(h/28). — [Pricing](https://platform.claude.com/docs/en/about-claude/pricing); [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)

### Inferences
Assumptions (mine): Task A has 20 calls x (300 in + 50 out), giving 6,000 input and 1,000 output tokens. Task B has 11 calls x (2,730 image + ~500 prompt/schema = 3,230 input) + 2,000 output, giving 35,530 input and 22,000 output tokens.

| Model | A input | A output | A total | B input | B output | B total | **A+B total** | A+B with Batch (-50%) |
|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 ($0.10/$0.50) | $0.0006 | $0.0005 | $0.0011 | $0.0036 | $0.0110 | $0.0146 | **≈ $0.016** | ≈ $0.008 |
| Sonnet 5.5 ($2/$10) | $0.012 | $0.010 | $0.022 | $0.071 | $0.220 | $0.291 | **≈ $0.31** | ≈ $0.16 |
| Opus 5.5 ($4/$20) | $0.024 | $0.020 | $0.044 | $0.142 | $0.440 | $0.582 | **≈ $0.63** | ≈ $0.31 |

- Per-request averages over 31 calls: Haiku about $0.0005, Sonnet about $0.010, Opus about $0.020.
- What could push actual cost up:
  - Thinking tokens are billed as output. Opus 5.5 cannot disable thinking, so its real output count may well exceed the assumed 50 and 2,000.
  - The hidden structured-outputs system prompt adds input tokens.
  - The newer tokenizer counts about 30% more tokens per text than older models.
  - Even at 2–3x, Opus stays under $2.
- Batch pricing is incompatible with the wrapper's `fallbacks` parameter unless that parameter is removed.

### Gaps
- Actual token counts depend on the prompt and schema text and on adaptive thinking volume. These can only be measured with the token-counting endpoint or a real run, and no API calls were made.

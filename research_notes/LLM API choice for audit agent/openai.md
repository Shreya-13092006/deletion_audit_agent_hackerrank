# OpenAI API as an option for (A) multilingual deletion-intent classification and (B) one-time screenshot-to-JSON extraction (state as of 2026-10-25)

Access date for all sources: 2026-10-25. Docs research only; no API calls were made. `platform.openai.com/docs/*` now 301-redirects to `developers.openai.com/api/docs/*`. Unless noted otherwise, every fact below comes from official OpenAI docs. Third-party sources are marked as such.

## Which current OpenAI model IDs fit task A and task B (including mini/nano tiers)?

### Takeaway
The current lineup no longer leads with "mini/nano". It uses three tiers: **Astra** (top), **Sol** (mid) and **Luna** (cheapest). The models page features `gpt-6-astra`, `gpt-6.1-sol` and `gpt-6-luna`, and all three take text and image input. Older mini and nano IDs (`gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-4.1-mini`/`-nano`, `gpt-5-mini`/`-nano`) are still priced on the pricing page. For task A, `gpt-6-luna` is the natural cheap choice. For task B, the strongest vision-capable model is `gpt-6-astra`, with `gpt-6.1-sol` as the cheaper "near-Astra" option.

### Cited Findings
- Featured flagship models: `gpt-6-astra` ("Our most capable model for the most demanding work"), `gpt-6.1-sol` ("Near-Astra performance for complex work at a lower cost") and `gpt-6-luna` ("Our most efficient model for focused, high-volume tasks"). The page says "All latest OpenAI models support text and image input." — [OpenAI Models](https://developers.openai.com/api/docs/models)
- Release timeline from the changelog:
  - Jul 9, 2026: the GPT-5.6 family launched (Sol/Terra/Luna; the `gpt-5.6` alias routes to `gpt-5.6-sol`).
  - Sep 3: GPT-6 Astra launched. It drops `none` reasoning effort and custom `temperature`/`top_p`.
  - Sep 22: GPT-6 Sol and GPT-6 Luna launched ("These reasoning models accept text and image inputs").
  - Sep 29: GPT-6.1 Sol launched.
  - Oct 8: GPT-6.1 Sol gained `service_tier: "ultrafast"`.
  - [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)
- `gpt-6-luna`:
  - Single snapshot; 1,050,000-token context (922,000 max input); 128,000 max output; knowledge cutoff May 18, 2026.
  - Text+image in, text out.
  - `reasoning.effort` supports `none`, `low`, `medium` (default), `high`, `xhigh`, `max`.
  - Supports structured outputs, function calling, streaming and prompt caching.
  - Endpoints: Responses, Chat Completions (function calling only at effort `none`) and Batch.
  - [gpt-6-luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
- `gpt-6.1-sol`:
  - Single snapshot; 1,050,000 context (922,000 max input); 128,000 max output; knowledge cutoff Apr 30, 2026.
  - Text+image in, text out.
  - Reasoning effort `low`–`max`. The page says "The `none` and `minimal` reasoning efforts are not supported."
  - Supports structured outputs. Endpoints: Responses, Chat Completions ("without tool calling") and Batch.
  - [gpt-6.1-sol model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- `gpt-6-sol`: knowledge cutoff Apr 20, 2026; image input; structured outputs; reasoning effort includes `none`; endpoints Chat Completions, Responses and Batch. — [gpt-6-sol model page](https://developers.openai.com/api/docs/models/gpt-6-sol)
- Older or cheaper text+vision IDs still on the pricing page: `gpt-5.6-sol/terra/luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.2`, `gpt-5.1`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `o3`, `o4-mini`. — [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)
- The vision guide calls `gpt-5-mini`, `gpt-5-nano` and `o4-mini` deprecated ("The first two and the last are deprecated"). — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
- Third-party news coverage (not official) says Sol/Luna launched Sep 22, 2026, and that an OpenAI Help Center page still called them GPT-5.6 models at one point. — [letsdatascience.com](https://letsdatascience.com/news/openai-expands-gpt-56-options-in-chatgpt-360ebb75); [technews.tw](https://technews.tw/2026/09/23/openai-launches-gpt-6-sol-and-luna-boasting-lower-cost-and-fewer-mistakes/)
- Rumors (not official, ignore for planning):
  - Reuters, via secondary sources, reported a shelved "Astra" release.
  - A "Terra" GPT-6.x model is rumored.
  - The official models page lists `gpt-6-astra` as live, which contradicts the "shelved" report.
  - [virginiabusiness.com](https://virginiabusiness.com/openai-shelves-gpt-6-1-astra-release-safety-concerns/); [testingcatalog.com](https://www.testingcatalog.com/openai-prepares-gpt-6-1-terra-microsoft-code.md)

### Inferences
- Task A (short multilingual classification, 0–20 calls): `gpt-6-luna` with `reasoning.effort: "none"` or `"low"` and strict JSON schema. It is the cheapest current-generation model, and `none` effort avoids hidden reasoning-token cost and latency. `gpt-6-sol` is a step-up option that also supports `none`.
- Task B (dense screenshot OCR into JSON, 11 images): `gpt-6-astra` is the strongest option, and it is the only GPT-6 model whose image-token rules are fully documented. `gpt-6.1-sol` is about 5x cheaper per token and is described as near-Astra.
- With 11 images, cost differences are a few cents to about $1.50 at most (see last section). Accuracy should drive the choice, not price.
- `gpt-5-mini` and `gpt-5-nano` should be avoided because they are deprecated.

### Gaps
- I found no official benchmark comparing Astra, Sol and Luna on OCR or on multilingual intent classification.
- I found no official OpenAI announcement blog post for GPT-6 (only the changelog and model pages were fetched).

## Per-million-token prices, and how image inputs are tokenized (tokens for one ~1800x1150 PNG at high detail)

### Takeaway
Standard prices per 1M tokens (input / cached input / output):

| Model | Input | Cached input | Output |
|---|---|---|---|
| `gpt-6-astra` | $10 | $1 | $50 |
| `gpt-6.1-sol` | $2 | $0.10 | $10 |
| `gpt-6-sol` | $2 | $0.20 | $10 |
| `gpt-6-luna` | $0.10 | $0.01 | $0.50 |

Batch is 50% off. Images on newer models are billed as 32x32-px patches times a multiplier. One 1800x1150 image comes to about **2,463 input tokens** on patch-based models with a 1.2 multiplier.

### Cited Findings
- **Standard pricing (≤272K input context), per 1M tokens (input / cached / output)** — [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)

| Model | Input | Cached input | Output |
|---|---|---|---|
| gpt-6-astra | $10.00 | $1.00 | $50.00 |
| gpt-6.1-sol | $2.00 | $0.10 | $10.00 |
| gpt-6-sol | $2.00 | $0.20 | $10.00 |
| gpt-6-luna | $0.10 | $0.01 | $0.50 |
| gpt-5.6-sol | $4.00 | $0.40 | $20.00 |
| gpt-5.6-terra | $2.00 | $0.20 | $12.00 |
| gpt-5.6-luna | $0.20 | $0.02 | $1.20 |
| gpt-5.5 | $5.00 | $0.50 | $30.00 |
| gpt-5.4 | $2.50 | $0.25 | $15.00 |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 |
| gpt-5.4-nano | $0.20 | $0.02 | $1.25 |
| gpt-5.1 / gpt-5 | $1.25 | $0.125 | $10.00 |
| gpt-5-mini | $0.25 | $0.025 | $2.00 |
| gpt-5-nano | $0.05 | $0.005 | $0.40 |
| gpt-4.1 | $2.00 | $0.50 | $8.00 |
| gpt-4.1-mini | $0.40 | $0.10 | $1.60 |
| gpt-4.1-nano | $0.10 | $0.025 | $0.40 |
| o3 | $2.00 | $0.50 | $8.00 |
| o4-mini | $1.10 | $0.275 | $4.40 |

- **Batch API** is 50% of Standard. For example, gpt-6-astra is $5/$25, gpt-6.1-sol $1/$5, gpt-6-luna $0.05/$0.25, gpt-5.4-mini $0.375/$2.25 and gpt-5.4-nano $0.10/$0.625. The Flex table does not list the GPT-6 family. — [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)
- **Other pricing notes** — [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)
  - "Priority processing was renamed Fast mode on July 30, 2026."
  - Regional (data residency) endpoints carry a 10% uplift.
  - GPT-5.6 Sol has a promotional price "available at least through November 21, 2026" (the promo figure was not captured).
- **Patch-based image tokenization (newer models)** — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
  - The image is first fit to the model and detail pixel limit, then `patch_count = ceil(width/32)×ceil(height/32)`.
  - If the patch count exceeds the patch budget, the image is scaled by `shrink_factor = sqrt((32^2 * patch_budget)/(width*height))`.
  - Tokens = patches × model multiplier, rounded up.
  - Images over 30,000 patches after processing are rejected.
- **Detail levels** are `low`, `high`, `original` and `auto`. The default is `auto`. — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
- **Per-model image rules** — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
  - `gpt-6-astra`: `high` = 2,500-patch budget, 65,535 px max dimension; `original`/`auto` keep dimensions. Multiplier 1.2.
  - `gpt-5.6-*`: `high` fits 2048x2048 and 2,500 patches. Multiplier 1.2.
  - `gpt-5.4`/`-mini`/`-nano`: `high` = 2,500 patches and 2048 px; `original` = 10,000 patches and 6000 px; `low` can cost more than `high` (6,144-patch budget). Multiplier 1.2.
  - `gpt-4.1-mini` multiplier 1.62; `gpt-5-nano` 1.5; `gpt-4.1-nano` 2.46; `o4-mini` 1.72.
- **Worked examples** (gpt-6-astra, high): 1024x1024 gives 1,229 tokens; 2048x2048 is resized to 1600x1600 and gives 3,000 tokens. — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
- **Tile-based tokenization (older models: gpt-5.1, gpt-4.1, gpt-4o, gpt-4o-mini)** — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
  - The image is fit to a 2048 square, then the shortest side is scaled to 768.
  - Cost = base tokens + per-512-px tile tokens.
  - gpt-4.1: 85 base + 170 per tile. gpt-5.1: 70 base + 140 per tile.
- The vision guide gives **no image-token rules for `gpt-6.1-sol`, `gpt-6-sol` or `gpt-6-luna`**. They are absent from its sizing and multiplier tables. — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)

### Inferences
These are my arithmetic using the formulas above.

- **1800x1150 PNG on patch-based models at `high`.** ceil(1800/32)=57 and ceil(1150/32)=36, so the image is 2,052 patches. That is under the 2,500 budget, so no downscale happens.
  - Multiplier 1.2 (gpt-6-astra, gpt-5.6-*, gpt-5.4-mini/nano): ceil(2052×1.2) = **2,463 tokens**.
  - Multiplier 1.5 (gpt-5-nano): 3,078 tokens.
  - Multiplier 1.62 (gpt-4.1-mini): 3,325 tokens.
  - Multiplier 2.46 (gpt-4.1-nano): 5,048 tokens.
  - On gpt-6-astra, `auto`/`original` also give 2,463 tokens, because the image is under all limits.
- **The same image on tile-based models.** The short side is scaled to 768, giving about 1202x768, or 3x2 = 6 tiles.
  - gpt-4.1: 85+6×170 = 1,105 tokens.
  - gpt-5.1: 70+6×140 = 910 tokens.
  - These lower counts come from downscaling, which is bad for small digits.
- **GPT-6 Sol and Luna.** Their image-token rules are not documented. Assuming they follow the gpt-5.6 and gpt-6-astra pattern (1.2 multiplier, 2,500-patch high budget), the image is about 2,463 tokens. This is unverified.

### Gaps
- Official image-token multiplier and patch budget for gpt-6.1-sol, gpt-6-sol and gpt-6-luna are not in the vision guide.
- The GPT-5.6 Sol promotional price amount was not captured.
- Reasoning-token billing was not re-verified on the fetched pages. Standard OpenAI practice is that reasoning tokens bill as output.

## Is there a free tier or free API credit? What are the rate limits for a new account?

### Takeaway
The official rate-limits guide lists a **Free** usage tier: no spend required, "allowed geography" only, capped at $100/month of usage. It does not say which models a Free-tier org can call or at what RPM/TPM. No signup credit is documented. Since Oct 6, 2026, the paid tiers are **Build ($5 purchased) / Launch ($100) / Grow ($500)**. At Build, Luna gets 5,000 RPM / 2M TPM, and Astra/Sol/Terra get 5,000 RPM / 1M TPM. No RPD limits are listed.

### Cited Findings
- **Tier table** — [OpenAI Rate limits guide](https://developers.openai.com/api/docs/guides/rate-limits)

| Tier | Qualification | Monthly usage limit |
|---|---|---|
| Free | "User must be in an allowed geography" | $100/month |
| Build | $5 in total credit purchases | $500/month |
| Launch | $100 | $5,000/month |
| Grow | $500 | $200,000/month |

- Tiers upgrade automatically as purchases reach each threshold. — [OpenAI Rate limits guide](https://developers.openai.com/api/docs/guides/rate-limits)
- **Build-tier limits:** Astra, Sol and Terra get 5,000 RPM and 1,000,000 TPM; Luna gets 5,000 RPM and 2,000,000 TPM. No Free-tier limits are given. — [OpenAI Rate limits guide](https://developers.openai.com/api/docs/guides/rate-limits)
- On Oct 6, 2026, OpenAI "Simplified API usage tiers from five to three" (Build, Launch, Grow). — [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)
- **gpt-6-luna per-tier limits** (RPM / TPM / batch queue) — [gpt-6-luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna)
  - Build: 5,000 / 2M / 20M
  - Launch: 10,000 / 10M / 1B
  - Grow: 30,000 / 180M / 15B
- **gpt-6.1-sol per-tier limits** (RPM / TPM) — [gpt-6.1-sol model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
  - Build: 5,000 / 1M
  - Launch: 10,000 / 4M
  - Grow: 15,000 / 40M
- **gpt-6-sol per-tier limits** (RPM / TPM / batch queue). There is no Free row. — [gpt-6-sol model page](https://developers.openai.com/api/docs/models/gpt-6-sol)
  - Build: 5,000 / 1M / 3M
  - Launch: 10,000 / 4M / 200M
  - Grow: 15,000 / 40M / 15B
- The only API items the pricing page lists as free are `omni-moderation-latest`, 1 GB of file-search storage and 1 GB/month of Agent Kit storage. — [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)
- The data-controls page describes a data-sharing opt-in but mentions no free tokens for it. — [OpenAI Your data](https://developers.openai.com/api/docs/guides/your-data)
- Third-party sources, older or conflicting: benchlm.ai (read Sep 14, 2026, before the restructure) describes legacy Tier 1–5 thresholds ($5/$50/$100/$250/$1,000) and "no free signup credit". Layer3Labs (Oct 10, 2026) confirms the Oct 6 Build/Launch/Grow restructure. — [benchlm.ai](https://benchlm.ai/free-tier/openai); [layer3labs.io](https://www.layer3labs.io/guides/openai-api-usage-tiers)

### Inferences
- For ~31 calls total, even the Build tier's limits are far beyond need, so rate limits are a non-issue.
- The practical minimum to get guaranteed model access is a $5 credit purchase (Build).
- Free-tier model access is undocumented, so do not plan around it.

### Gaps
- Free-tier model list and RPM/TPM/RPD are not published on the pages fetched.
- Whether "allowed geography" includes the participant's country is not stated.
- No RPD values exist for the new tiers.

## Structured outputs / JSON-schema enforcement: which models support it, including with image inputs?

### Takeaway
Strict JSON-schema Structured Outputs is supported on all the current models above: the GPT-6 model pages list `structured_outputs`, and the guide covers everything from gpt-4o-mini/gpt-4o-2024-08-06 onward. In the Responses API, set `text.format`. In Chat Completions, set `response_format: {type: "json_schema", ...}`. The docs do not explicitly address images combined with structured outputs, but both features are listed on the same model pages.

### Cited Findings
- Structured Outputs is available in "our latest large language models, starting with GPT-4o". The guide recommends starting with `gpt-6-astra`. Compatibility: "gpt-4o-mini, gpt-4o-2024-08-06, and later". Older models use JSON mode. — [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
- **Responses API:** `text: { format: { type: "json_schema", "strict": true, "schema": ... } }`. **Chat Completions:** `response_format: {type: "json_schema", ...}`. — [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
- **Schema rules** — [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
  - All fields must be `required`. Emulate optional fields with a `null` union.
  - `additionalProperties: false` is mandatory.
  - The root must be an object and cannot be `anyOf`.
  - Limits: 5,000 properties, 10 nesting levels, 120,000 characters of names/enums/consts, and 1,000 enum values (15,000-character cap when a single enum has more than 250 values).
  - `allOf`, `not`, `if`/`then`/`else`, `dependentRequired` and `dependentSchemas` are unsupported and return an error.
- **Refusals** do "not necessarily follow the schema". A `refusal` field is returned instead, so check it before parsing. Responses can also be incomplete when they hit `max_output_tokens`. — [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
- `gpt-6-luna`, `gpt-6.1-sol` and `gpt-6-sol` each list both structured outputs and image input as supported features. — [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna); [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol); [gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol)
- No structured-output changes appear in the changelog for Jul–Oct 2026. — [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)

### Inferences
- Strict schema guarantees shape, not truth. A misread `backup_9287` still validates as a string, so deterministic post-validation (regex on IDs and emails, cross-checks against SQL/CSV data) is still required.
- For task B, set `max_output_tokens` well above ~2,000 plus reasoning headroom, so the JSON is not truncated (an "incomplete" response).

### Gaps
- No official statement was found that explicitly confirms strict json_schema plus image input in one request, or caveats about it. It is implied by the feature lists, not stated.

## Data usage and retention policy for API inputs

### Takeaway
API data is **not used for training by default**. Abuse-monitoring logs are kept **up to 30 days**. The Responses API stores application state for at least 30 days by default (`store=true`), so set `store: false` or use Chat Completions to avoid it. ZDR and Modified Abuse Monitoring require OpenAI approval. Image inputs are always CSAM-scanned.

### Cited Findings
- "data sent to the OpenAI API is not used to train or improve OpenAI models" unless you explicitly opt in. — [OpenAI Your data](https://developers.openai.com/api/docs/guides/your-data)
- Abuse-monitoring logs are retained up to 30 days, unless law or harm prevention requires longer. — [OpenAI Your data](https://developers.openai.com/api/docs/guides/your-data)
- **Per-endpoint retention** — [OpenAI Your data](https://developers.openai.com/api/docs/guides/your-data)
  - `/v1/responses`: application state is kept for at least 30 days by default or when `store=true`. Background requests with `store=false` are held about 10 minutes.
  - `/v1/chat/completions`: no application state, except audio outputs (1 hour).
  - `/v1/files` and `/v1/batches`: kept "until deleted".
- **ZDR** (approval only): excluded from abuse logs, and `store` is forced to false. **MAM** (approval only): excluded from abuse logs, except image and file inputs in rare cases. — [OpenAI Your data](https://developers.openai.com/api/docs/guides/your-data)
- Image and file inputs are scanned for CSAM on submission. Flagged content is retained even under ZDR or MAM. — [OpenAI Your data](https://developers.openai.com/api/docs/guides/your-data)

### Inferences
- The challenge data is fictional, so privacy risk is low.
- To minimize residue, send requests with `store: false`. Note that the Batch API persists the input and output files until you delete them.

### Gaps
- None material.

## Known reliability caveats: OCR of small digits (9/g, I/1), dark-theme screenshots

### Takeaway
The official vision guide lists general limitations: small text, non-Latin scripts (Japanese and Korean explicitly), color- or style-dependent visuals, spatial localization and occasional incorrect descriptions. It recommends enlarging text and using `detail: "original"` for OCR. It does **not** specifically mention 9/g or I/1 confusion, or dark themes. A Sep 25, 2026 fix addressed an image-encoding bug that had degraded GPT-6 Sol/Luna vision.

### Cited Findings
- "Enlarge text within the image to improve readability"; "using `"detail": "original"` can also help performance". For "tasks that require fine visual detail or precise coordinates, such as optical character recognition (OCR)", use `detail: "original"` when supported. — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
- "The model may not perform optimally when handling images with text of non-Latin alphabets, such as Japanese or Korean." — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
- Other limitations quoted from the guide — [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)
  - "may struggle to understand graphs or text where colors or styles ... vary"
  - "struggles with tasks requiring precise spatial localization"
  - "may generate incorrect descriptions or captions"
  - "may misinterpret rotated or upside-down text"
  - "Images may be resized before analysis, including with `original` detail"
  - "may give approximate counts"
- Sep 25, 2026: a fix for "a bug in image encoding that degraded image understanding" improved GPT-6 Sol and Luna on visual tasks. OpenAI recommends rerunning evaluations of image-input workflows. — [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)
- Jul 9, 2026: GPT-5.6 accepts images at "their original dimensions" with `original`/`auto` detail. — [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog)

### Inferences
- On 1800x1150 dense tables, tile-based older models (gpt-4.1, gpt-5.1) downscale the image to about 1202x768. That raises the risk of 9/g and I/1 confusions, so prefer patch-based models with `high`/`original`, which avoid downscaling at this size.
- Optional pre-processing: crop and upscale the table regions, and invert dark themes. This follows OpenAI's "enlarge text" advice.
- Cross-validate extracted IDs against known identifiers from text and SQL evidence. Any screenshot-only ID should be flagged.

### Gaps
- No official documentation was found on confusion between specific characters (9/g, I/1, 0/O) or on dark-theme screenshot accuracy.
- No official OCR accuracy benchmarks per model were found.

## Estimated total cost: ~20 text calls (300 in / 50 out) and 11 image calls (~2,000 out)

### Takeaway
At Standard prices the whole job costs roughly $0.015 with `gpt-6-luna` for both tasks, about $0.31 with `gpt-6.1-sol` and about $1.54 with `gpt-6-astra`. A practical mix (Luna for A, Astra for B) is about **$1.43**. Batch halves all of these. Hidden reasoning tokens are the main variable.

### Cited Findings
- Prices: [OpenAI Pricing](https://developers.openai.com/api/docs/pricing)
- Image-token formula: [OpenAI Images & Vision guide](https://developers.openai.com/api/docs/guides/images-vision)

### Inferences
These are my arithmetic, at Standard prices.

**Assumptions**
- Text job: 20 × 300 = 6,000 input tokens and 20 × 50 = 1,000 output tokens.
- Image job: each call is 2,463 image tokens plus about 500 prompt and schema tokens, so about 2,963 input. In total that is 11 × 2,963 = 32,593 input tokens and 11 × 2,000 = 22,000 output tokens.
- Reasoning tokens are excluded.

| Model | Task A cost | Task B cost | Both on one model |
|---|---|---|---|
| gpt-6-luna ($0.10/$0.50) | $0.0011 | $0.0143 | **≈ $0.015** |
| gpt-5.4-nano ($0.20/$1.25) | $0.0025 | $0.034 | ≈ $0.036 |
| gpt-4.1-mini ($0.40/$1.60; 3,325 image tokens) | $0.004 | $0.052 | ≈ $0.056 |
| gpt-5.4-mini ($0.75/$4.50) | $0.009 | $0.123 | ≈ $0.13 |
| gpt-6.1-sol / gpt-6-sol ($2/$10) | $0.022 | $0.285 | ≈ $0.31 |
| gpt-6-astra ($10/$50) | $0.110 | $1.426 | ≈ $1.54 |

- **Recommended mix:** Luna for A ($0.0011) and Astra for B ($1.43) comes to about $1.43. Luna for A and 6.1-sol for B is about $0.29.
- **Reasoning overhead:**
  - Reasoning tokens are, by standard OpenAI practice (not re-verified on the fetched pages), billed as output.
  - Astra and 6.1-sol cannot run at effort `none`. If each image call adds about 2,000 reasoning tokens at `low`, Astra's Task B cost rises by about $1.10, to roughly $2.50 total. 6.1-sol rises by about $0.22.
  - Luna and 6-sol at `none` add nothing.
- **Batch API (50% off):** halves every figure, but completion can take up to 24 hours.
- **Prompt caching:** the cached-input discount on a repeated system prompt and schema saves only fractions of a cent here.

### Gaps
- Actual output length and reasoning-token usage per call are unknown without test calls (not allowed here).
- The image tokens for gpt-6.1-sol and gpt-6-luna assume the undocumented 1.2-multiplier rule.

# Google Gemini API (Developer API / AI Studio) for (A) multilingual deletion-intent classification and (B) one-time screenshot extraction — state as of late October 2026

Access date for all sources: 2026-10-25. No API calls were made; documentation research only. Page "last updated" stamps are quoted where the page showed one.

Note on API surface: Google's docs now lead with the **Interactions API** (`client.interactions.create`, `response_format`, `input` array), "recommended for all new projects" and "Generally Available" as of June 2026; "the original generateContent API remains fully supported" (needs `google-genai` >= 2.3.0 for Interactions) — [Interactions overview, updated 2026-10-15](https://ai.google.dev/gemini-api/docs/interactions). generateContent docs are now labelled "(Legacy)" — [Structured outputs, Generate Content API (Legacy), updated 2026-10-19](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).

## 1. Current stable model IDs and which tier fits A and B

### Takeaway
Stable, free-tier-eligible choices are `gemini-3.8-flash` / `gemini-3.6-flash` (Flash) and `gemini-3.5-flash-lite` / `gemini-3.1-flash-lite` (Flash-Lite); the only Pro options are `gemini-3.1-pro-preview` (preview, no free tier) and legacy `gemini-2.5-pro`. Flash-Lite is enough for (A); Flash (3.8) is the safer pick for dense-table OCR in (B).

### Cited Findings
- Models page (updated 2026-10-22) lists: Gemini 4 stable `gemini-4-argon` (flagship reasoning, 1M context); Gemini 3 stable Flash `gemini-3.8-flash` (New), `gemini-3.6-flash`; stable Flash-Lite `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`; no stable Gemini 3 Pro; preview `gemini-3-flash-preview`, `gemini-3.1-pro-preview` — [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- Gemini 2.5 models (`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`) "are not deprecated", are limited to users who used them previously, and "will continue to be served until further notice" — [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- Shut down: `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-3.1-flash-lite-preview`, `gemini-3-pro-preview`, among others — [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- No `-latest` aliases are listed (only `gemini-flash-latest` mentioned as a naming-convention example) — [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- Release dates: `gemini-3.8-flash` 2026-09-02; `gemini-3.6-flash` and `gemini-3.5-flash-lite` 2026-07-21; `gemini-3.1-flash-lite` 2026-05-07; `gemini-3.1-pro-preview` 2026-02-19; `gemini-3-flash-preview` 2025-12-17 — [Deprecations, updated 2026-10-22](https://ai.google.dev/gemini-api/docs/deprecations)
- For new projects Google recommends "3.5 Flash-Lite or 3.8 Flash" — [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations)

### Inferences
- (A) ~20 short classification calls: `gemini-3.5-flash-lite` (stable, free tier, cheap, reportedly higher free RPD) is the natural fit; `gemini-3.8-flash` if ambiguity handling in JA/KO needs more reasoning.
- (B) 11 dense dark-theme screenshots: `gemini-3.8-flash` (stable, free tier) with higher media resolution; Pro-tier is only available as preview (3.1 Pro Preview, paid only) or legacy 2.5 Pro (not available to new users).

### Gaps
- Models page did not list context windows/modalities per model except Gemini 4 Argon; not verified for Flash/Flash-Lite.
- No public quality benchmark comparison for multilingual intent classification or screenshot OCR was retrieved.

## 2. Free-tier availability, rate limits, and paid prices

### Takeaway
All stable Flash/Flash-Lite models (and 2.5 Pro) are "Free of charge" on the free tier; Gemini 4 Argon and 3.1 Pro Preview are paid-only. Official docs no longer publish numeric free-tier RPM/TPM/RPD (they point to AI Studio); the only figure found is an unofficial 20 RPD for 3.8 Flash and 500 RPD for Flash-Lite.

### Cited Findings
Paid prices per 1M tokens (Standard; text/image input / output incl. thinking; batch is 50%) — [Pricing, updated 2026-10-22](https://ai.google.dev/gemini-api/docs/pricing):

| Model | Free tier | Input | Output | Batch in/out |
|---|---|---|---|---|
| gemini-4-argon | No | $2.00 (to 2026-11-30), $4.00 from 2026-12-01 | $10.00, $20.00 from 2026-12-01 | $1/$5 → $2/$10 |
| gemini-3.8-flash | Yes | $0.75 (to 2026-12-31), $1.50 from 2027-01-01 | $3.75 → $7.50 | $0.375/$1.875 → $0.75/$3.75 |
| gemini-3.6-flash | Yes | same as 3.8 Flash | same | same |
| gemini-3.5-flash-lite | Yes | $0.30 | $2.50 | $0.15/$1.25 |
| gemini-3.1-flash-lite | Yes | $0.25 | $1.50 | $0.125/$0.75 |
| gemini-3.1-pro-preview | No | $2.00 (<=200k) / $4.00 | $12.00 / $18.00 | $1/$6 |
| gemini-3-flash-preview | Yes | $0.50 | $3.00 | $0.25/$1.50 |
| gemini-2.5-pro | Yes | $1.25 (<=200k) / $2.50 | $10.00 / $15.00 | $0.625/$5 |
| gemini-2.5-flash | Yes | $0.30 | $2.50 | $0.15/$1.25 |
| gemini-2.5-flash-lite | Yes | $0.10 | $0.40 | $0.05/$0.20 |

- Rate-limits page (updated 2026-10-15) gives no per-model free-tier or Tier 1 RPM/TPM/RPD numbers; it directs users to AI Studio, where limits "update automatically" — [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- Limits are "applied per project, not per API key"; dimensions are RPM, input TPM, RPD (some models also IPM/TPD); "RPD quotas reset at midnight Pacific time"; exceeding any one triggers a rate-limit error — [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- Tier 1 has a $10 spend-based limit per rolling 10-minute window (not applicable to free) — [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- UNOFFICIAL: a developer forum post dated 2026-09-03 states "the free tier limit of 20 RPD" for Gemini 3.8 Flash and cites 500 RPD for Flash-Lite; no Google staff reply — [Google AI Developers Forum](https://discuss.ai.google.dev/t/gemini-3-8-flash-free-tier-20-rpd-is-too-limited-for-practical-evaluation/180609). A third-party Korean note says the 20/day figure on the AI Studio screen was for Gemini 3.5 Flash, not 3.8 Flash — conflicting/unverified ([search result, tilnote.io](https://tilnote.io/pages/6a51b3398d9a59d14c1c174c)).
- Billing tiers: Free (active project, no billing); Tier 1 = linked billing account (monthly cap $250); Tier 2 = $100 paid + 3 days; Tier 3 = $1,000 paid + 30 days. Moving to paid requires prepaying at least $5 (Prepay default for new users since 2026-03-23); credits expire after 12 months; at $0 balance requests fail with HTTP 402 — [Billing, updated 2026-09-28](https://ai.google.dev/gemini-api/docs/billing)

### Inferences
- If the 20 RPD figure for 3.8 Flash is accurate, 31 calls (20 text + 11 image) would not fit in one day on 3.8 Flash; splitting (A) onto Flash-Lite and (B) onto 3.8 Flash (11 calls) would fit. Pipeline should handle 429s with backoff and cache results.
- Scheduled price doubling for 3.8/3.6 Flash on 2027-01-01 does not affect an October 2026 run.

### Gaps
- Official numeric free-tier RPM/TPM/RPD per model could not be verified (only visible in the logged-in AI Studio rate-limit page).

## 3. Image input tokenization and limits

### Takeaway
On Gemini 3.x/4 models image cost is set by `media_resolution`: default 1,120 tokens/image, `ultra_high` 2,240; on 2.5 models a ~1800x1150 image tiles to about 6 x 258 = ~1,548 tokens. Inline requests are capped at 20 MB total.

### Cited Findings
- Gemini 4/3 `media_resolution` levels and max image tokens: `unspecified` (default) 1120, `low` 280, `medium` 560, `high` 1120, `ultra_high` 2240; `ultra_high` only settable per content item — [Media resolution, updated 2026-10-13](https://ai.google.dev/gemini-api/docs/media-resolution)
- For PDFs `medium` is recommended ("quality typically saturates at `medium`"); `high` "rarely improves OCR results for standard documents" — [Media resolution](https://ai.google.dev/gemini-api/docs/media-resolution)
- Interactions API sets it per item via a `"resolution"` key; generateContent exposes `MediaResolution.level` enum `MEDIA_RESOLUTION_UNSPECIFIED/LOW/MEDIUM/HIGH/ULTRA_HIGH` — [Media resolution](https://ai.google.dev/gemini-api/docs/media-resolution); [API reference](https://ai.google.dev/api/generate-content)
- Earlier-model tiling: images <=384 px both sides = 258 tokens; larger images tiled into 768x768 tiles at 258 tokens each; crop unit = floor(min(w,h)/1.5) (example 960x540 → 6 tiles ≈ 1,548 tokens) — [Image understanding, updated 2026-09-23](https://ai.google.dev/gemini-api/docs/image-understanding)
- Limits: max 3,600 image files per request; inline data counts toward 20 MB total request size (use File API beyond that); MIME types PNG, JPEG, WEBP, HEIC, HEIF — [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- Tips: put text prompt before the single image; higher `media_resolution` improves reading fine text at more tokens/latency — [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)

### Inferences
- 1800x1150 on 2.5 models: crop unit 766 → ~3x2 = 6 tiles ≈ 1,548 tokens (my application of the documented formula). On 3.x Flash: ~1,120 tokens default, 2,240 at `ultra_high`.
- Dense small-font tables (unlike standard documents) may benefit from `high`/`ultra_high`; this is untested. A ~1800x1150 PNG is well under 20 MB, so inline upload is fine.

### Gaps
- Docs state the `unspecified` token count differs for pre-Gemini-3 models but give no 2.5 media_resolution numbers.

## 4. Structured output (JSON schema), including with images

### Takeaway
All listed current models support schema-constrained JSON output (syntactically valid JSON guaranteed) via `response_mime_type="application/json"` + `response_json_schema` (generateContent) or `response_format` with a schema (Interactions). A JSON Schema subset is supported; some constraints are silently stripped. Docs do not explicitly address combining it with image input.

### Cited Findings
- generateContent: set `response_json_schema` (REST `responseFormat.text.schema`) plus JSON MIME type; Python example passes `Recipe.model_json_schema()` to `generate_content(model="gemini-3.8-flash")` and parses with `model_validate_json(response.text)` — [Structured outputs (Legacy), updated 2026-10-19](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- Interactions API: `response_format` with `"type": "text"`, `"mime_type": "application/json"`, and the schema in `schema` — [Structured outputs, updated 2026-10-21](https://ai.google.dev/gemini-api/docs/structured-output)
- Supported types: string, number, integer, boolean, object, array, null (via type arrays). Keywords: title, description, properties, required, additionalProperties, enum, format, minimum, maximum, items, prefixItems, minItems, maxItems; `anyOf` and `$ref` appear in examples — [Structured outputs (Legacy)](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- Not enforced, stripped without error: minLength, maxLength, minProperties, maxProperties, uniqueItems, contains, minContains, maxContains; very large/deeply nested schemas (large maxItems, many anyOf branches, many enum values) may return 400 INVALID_ARGUMENT — [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- Output key order follows schema order (2.0 models needed explicit propertyOrdering); output is syntactically valid JSON but not guaranteed semantically correct — validate in code — [Structured outputs (Legacy)](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- Model support list includes Gemini 4 Argon, 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 3.1 Pro Preview, 2.5 Pro/Flash/Flash-Lite — [Structured outputs (Legacy)](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- Structured output + built-in tools is preview-only, Gemini 3/4 only — [Structured outputs (Legacy)](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- Image-understanding docs show JSON schema output in bounding-box examples with images — [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- Older `responseSchema` (OpenAPI subset) still appears in API reference examples; a GitHub issue (checked 2026-07-22) reports the reference marks `responseSchema` deprecated in favour of JSON Schema / responseFormat; a third-party proxy issue reports `responseJsonSchema` 400s on one forwarding path — third-party, unverified — [API reference](https://ai.google.dev/api/generate-content); [GitHub issue](https://github.com/jeong-sik/masc/issues/27871); [GitHub issue](https://github.com/iBUHub/AIStudioToAPI/issues/278)
- JSON Schema support (anyOf, $ref) was announced on Google's blog — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs/)

### Inferences
- For (A) use an enum field (e.g. `"authorizes_deletion": {"enum": ["YES","NO"]}`) plus a short rationale; for (B) keep the schema flat (array of row objects with string fields) to avoid 400s, and validate regexes like `backup_\d+` client-side since `pattern` is not listed as supported.

### Gaps
- No explicit official statement that structured output works identically with image inputs (only implied by bounding-box examples).
- `pattern` keyword support not listed.

## 5. Free-tier data policy and regional restrictions

### Takeaway
Free (Unpaid) tier content is used to improve Google products and may be read by human reviewers; Google says not to submit sensitive, confidential, or personal information to Unpaid Services. Paid tier content is not used for improvement. Apps serving users in the EEA, Switzerland, or UK must use Paid Services.

### Cited Findings
- Unpaid Services: Google "uses the content you submit to the Services and any generated responses to provide, improve, and develop" products; "human reviewers may read, annotate, and process your API input and output" (disconnected from account/API key/project first) — [Gemini API Additional Terms, updated 2026-04-28, effective 2026-03-23](https://ai.google.dev/gemini-api/terms)
- "Do not submit sensitive, confidential, or personal information to the Unpaid Services." — [Terms](https://ai.google.dev/gemini-api/terms)
- Paid Services: "Google doesn't use your prompts" or "responses to improve our products"; processed under the Data Processing Addendum; prompts/responses logged "for a limited period of time" for abuse detection, safety, legal disclosure — [Terms](https://ai.google.dev/gemini-api/terms)
- Paid only when accessed through a Cloud project with an active billing account — [Terms](https://ai.google.dev/gemini-api/terms)
- "You may use only Paid Services when making API Clients available to users" in the EEA, Switzerland or UK; for such users Paid data terms apply to all Services including AI Studio and unpaid quota — [Terms](https://ai.google.dev/gemini-api/terms)
- Pricing table "Used to improve our products": Yes on free tier, No on paid, for every free-eligible model — [Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Once any API project has billing enabled, AI Studio prompts fall under Paid terms — [Billing](https://ai.google.dev/gemini-api/docs/billing)
- EEA countries, UK and Switzerland appear in the Gemini API / AI Studio available-regions list; the page does not discuss free-tier restrictions — [Available regions, updated 2026-10-22](https://ai.google.dev/gemini-api/docs/available-regions)

### Inferences
- The dataset is fictional, but request texts and screenshots contain realistic names/emails/phones. Literally, the "no personal information" rule targets real personal data; sending fictional PII to the free tier is likely permissible but means it may be human-reviewed and used for training. A $5 prepay (Tier 1) removes that concern and is the defensible choice for a "privacy audit" submission.
- A participant in the EEA/UK who is only running a local batch job (not making an API client available to users there) is not clearly covered by the Paid-only rule; this is a legal-interpretation question.

### Gaps
- Free-tier retention period is not stated in the Terms.

## 6. Reliability: preview vs stable, deprecation schedule

### Takeaway
Stable 3.x Flash/Flash-Lite models have no announced shutdown except `gemini-3.1-flash-lite` (earliest 2027-05-07); preview models get shut down (e.g. `gemini-3-pro-preview`, `gemini-3.1-flash-lite-preview` already gone), so pin a stable ID.

### Cited Findings
- `gemini-3.1-flash-lite` shutdown 2027-05-07 (replacement `gemini-3.5-flash-lite`); `gemini-3-flash-preview` replacement `gemini-3.6-flash`; no shutdown announced for 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Pro Preview, 2.5 models; listed dates are earliest possible with advance notice promised — [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- Already shut down: `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-3.1-flash-lite-preview`, `gemini-3-pro-preview` — [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- 2.5 models are restricted to previous users — [Gemini models](https://ai.google.dev/gemini-api/docs/models)

### Inferences
- For reproducibility pin `gemini-3.8-flash` / `gemini-3.5-flash-lite`, cache outputs (the repo already has `code/cache/image_facts.json` and `intent_cache.json`), and set temperature low; Gemini outputs are not bit-for-bit deterministic.

### Gaps
- No official uptime/SLA figure for the Developer API was retrieved.

## 7. Estimated cost: 20 text calls + 11 image calls

### Takeaway
Free tier: $0 (subject to RPD limits and free-tier data use). Paid: roughly $0.01–$0.11 total for the whole job on Flash/Flash-Lite, about $0.32 on 3.1 Pro Preview, before thinking tokens; minimum real outlay is the $5 prepay.

### Cited Findings
- Prices from [Pricing](https://ai.google.dev/gemini-api/docs/pricing); image tokens from [Media resolution](https://ai.google.dev/gemini-api/docs/media-resolution) and [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding); output price includes thinking tokens — [Pricing](https://ai.google.dev/gemini-api/docs/pricing); $5 minimum prepay — [Billing](https://ai.google.dev/gemini-api/docs/billing)

### Inferences (my arithmetic)
Assumptions: text = 20 x (300 in + 50 out) = 6,000 in / 1,000 out. Image = 11 x (image tokens + ~500 prompt/schema tokens) in, 11 x 2,000 = 22,000 out. Gemini 3.x at default resolution: 11 x 1,620 = 17,820 image-call input; total ~23,800 in / 23,000 out. 2.5 models (~1,548 tokens/image): ~28,500 in / 23,000 out. Thinking tokens excluded.

| Model | Approx. paid cost (standard) | Batch (50%) |
|---|---|---|
| gemini-3.8-flash (Oct–Dec 2026 price) | 23.8k x $0.75 + 23k x $3.75 ≈ $0.018 + $0.086 = **~$0.10** | ~$0.05 |
| gemini-3.8-flash at `ultra_high` (2,240 tok/img, ~36k in) | ~$0.027 + $0.086 ≈ **~$0.11** | ~$0.06 |
| gemini-3.5-flash-lite | $0.007 + $0.058 ≈ **~$0.065** | ~$0.03 |
| gemini-3.1-flash-lite | $0.006 + $0.035 ≈ **~$0.04** | ~$0.02 |
| gemini-2.5-flash | $0.009 + $0.058 ≈ **~$0.07** | — |
| gemini-2.5-flash-lite | $0.003 + $0.009 ≈ **~$0.012** | — |
| gemini-3.1-pro-preview (paid only) | $0.048 + $0.276 ≈ **~$0.32** | ~$0.16 |

- Per request (31 calls) on 3.8 Flash: ~$0.003; text calls alone ~$0.008 total on 3.8 Flash.
- Thinking can dominate: e.g. 1,000 thinking tokens per call adds 31k output tokens ≈ +$0.12 on 3.8 Flash, +$0.08 on 3.5 Flash-Lite. Configure a low thinking budget/level for (A).
- Free tier: $0; if 3.8 Flash really is 20 RPD, run (A) on Flash-Lite and (B) on 3.8 Flash, or spread over two days.

### Gaps
- Default thinking behaviour/token usage for 3.8 Flash and 3.5 Flash-Lite and how to disable it were not verified from docs in this pass.
- Official free-tier RPM/TPM/RPD numbers unverified (see section 2).

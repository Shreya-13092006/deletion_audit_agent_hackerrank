# Groq (GroqCloud) and free/low-cost routes (OpenRouter free, Mistral La Plateforme) for tasks A (multilingual intent classification) and B (11 screenshot extractions)

Access date for all sources: 2026-10-25. No API calls were made. Several vendor pages render partially to a fetcher, so some numbers come from secondary trackers and are flagged as such.

## Groq: production models, vision models and image limits, free-tier limits, prices, structured outputs

### Takeaway
As of late Oct 2026 Groq's production LLM lineup is down to openai/gpt-oss-120b and openai/gpt-oss-20b, plus Llama 3.1 8B and 3.3 70B. Those two Llama models are listed as deprecated for free and developer tiers as of 08/16/26. Every Llama 4 vision model is gone. The only self-serve vision model is the **preview** model `qwen/qwen3.8-27b`. Its limits are 3 images per request and 2,048 tokens per image, and it costs $0.80/$4.00 per 1M tokens. Strict JSON-schema mode works on gpt-oss-20b, gpt-oss-120b, qwen3.8-27b and muse-spark-open. That makes gpt-oss-20b or 120b a strong fit for A. Qwen3.8-27b is the only Groq option for B, and it is a preview model with a tight per-image token budget.

### Cited Findings
- Production models listed: llama-3.1-8b-instant, llama-3.3-70b-versatile (both 131K context, priced "Contact sales (Enterprise)"), openai/gpt-oss-120b (131K ctx, 65,536 max output, $0.15 in / $0.60 out per 1M), openai/gpt-oss-20b (131K, 65,536 max output, $0.075 / $0.30), and whisper-large-v3/-turbo — [Groq Models](https://console.groq.com/docs/models)
- Preview models listed: meta-models/muse-spark-open (131K, Enterprise pricing), minimaxai/minimax-m2.7, openai/gpt-oss-safeguard-20b ($0.075/$0.30), qwen/qwen3.8-27b (131K ctx, 16,384 max output, $0.80 in / $4.00 out, 20 MB max file), the Llama Prompt Guard 2 models and the Orpheus TTS models. "Preview models are for evaluation only and may be discontinued at short notice." — [Groq Models](https://console.groq.com/docs/models)
- Deprecations: llama-4-maverick-17b-128e-instruct shut down 03/09/26 and llama-4-scout-17b-16e-instruct 07/17/26 (replacement: gpt-oss-120b or qwen3.6-27b). qwen/qwen3-32b shut down 07/17/26. llama-3.3-70b-versatile and llama-3.1-8b-instant shut down 08/16/26 for free and developer tiers, with Enterprise committed-spend contracts unaffected (replacements: gpt-oss-120b / gpt-oss-20b). qwen/qwen3.6-27b shut down 09/14/26 and was succeeded by qwen/qwen3.8-27b. moonshotai/kimi-k2-instruct-0905 shut down 04/15/26. groq/compound and compound-mini shut down 09/21/26 — [Groq Deprecations](https://console.groq.com/docs/deprecations)
- Vision-capable models: qwen/qwen3.8-27b (text and image input) and meta-models/muse-spark-open (reasoning, text and image, "limited preview, contact Groq for access") — [Groq Vision](https://console.groq.com/docs/vision)
- Image limits: qwen3.8-27b allows 3 images per request at 2,048 tokens per image. muse-spark-open allows 5 images per request at up to 1,026 tokens per image depending on size. "Maximum allowed size for a request containing an image URL as input is 20MB" (larger requests return 400). The page gives no base64 limit and no max resolution — [Groq Vision](https://console.groq.com/docs/vision)
- JSON mode works with image input on qwen3.8-27b; the vision docs include an example that sends an image with `response_format` JSON mode — [Groq Vision](https://console.groq.com/docs/vision)
- qwen3.8-27b model card: status Preview, text and image in, 131,072 ctx, 16,384 max output, $0.80/$4.00 per 1M, up to 3 images, 20 MB, 2,048 tokens per image. It supports JSON Object Mode and JSON Schema Mode. It defaults to thinking mode; `reasoning_effort="none"` gives non-thinking instruct mode, and `reasoning_format` can be hidden or parsed. Multilingual support is described as "strong" — [Groq qwen3.8-27b](https://console.groq.com/docs/model/qwen/qwen3.8-27b)
- Structured outputs: strict mode (`strict: true`, constrained decoding, all fields required, `additionalProperties: false`) is available on openai/gpt-oss-20b, openai/gpt-oss-120b, qwen/qwen3.8-27b and meta-models/muse-spark-open. Best-effort mode (`strict: false`) is available on those plus gpt-oss-safeguard-20b, and "occasional 400 errors can occur". `json_object` mode guarantees only syntactically valid JSON. Streaming and tool use are not supported together with Structured Outputs. The page does not say whether strict mode works with image input — [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)
- Rate-limit table (labelled both "Free Plan Limits" and "base limits for the Developer plan", which the page itself leaves inconsistent): gpt-oss-120b, gpt-oss-20b and qwen3.8-27b each get 30 RPM / 1K RPD / 8K TPM / 200K TPD. gpt-oss-safeguard-20b gets 3 RPM / 1K RPD / 2K TPM / 200K TPD. Limits apply per organization, not per key or user. "Cached tokens do not count towards your rate limits." — [Groq Rate Limits](https://console.groq.com/docs/rate-limits) (fetched twice). Third-party summaries give the same 30/1K/8K/200K figures — [developersdigest](https://www.developersdigest.tech/models/free-api/groq), [eesel](https://eesel.ai/blog/groq-pricing)
- On a limit breach the API returns HTTP 429 with a `retry-after` header in seconds. `x-ratelimit-limit/remaining-requests` refer to RPD, `x-ratelimit-*-tokens` refer to TPM, and reset headers are included on every response — [Groq Rate Limits](https://console.groq.com/docs/rate-limits)
- groq.com/pricing gave no per-model figures to the fetcher (the page rendered as marketing copy). The prices above come from the docs Models table — [Groq Pricing](https://groq.com/pricing)

### Inferences
- **Task A on Groq:** use `openai/gpt-oss-20b` (cheapest, production) or `openai/gpt-oss-120b` (stronger multilingual reasoning, production) with `strict: true`. 20 calls sit far inside 30 RPM / 1K RPD / 200K TPD. gpt-oss models are reasoning models, so reasoning tokens add to output and TPM. Keep reasoning effort low and set max_tokens.
- **Task B on Groq:** the only self-serve option is `qwen/qwen3.8-27b`, which is a preview model. At 2,048 tokens per image, a dense 1800x1150 table will likely be downscaled internally and small IDs such as `backup_9287` may become unreadable. The request limit of 3 images supports tiling, for example splitting each screenshot into 2–3 crops sent in one request. Use `reasoning_effort="none"` so thinking tokens do not consume the 16K output budget or the 8K TPM.
- With TPM at 8K on the free plan, one B request (about 2.5K input plus 2K output) can only go out about once per minute. The 11 screenshots need roughly 11–15 minutes at the free tier, or a paid Developer plan.
- The fetched page says "Developer plan" and "Free Plan" at the same time. Treat 30/1K/8K/200K as the likely free-tier figures, and confirm them in console.groq.com/settings/limits.

### Gaps
- Whether strict JSON-schema mode (as opposed to json_object) is supported with image input on qwen3.8-27b is not stated in official docs.
- Base64 image size limit and maximum resolution for Groq vision are not documented on the fetched pages.
- groq.com/pricing could not be parsed, so the Models table prices could not be cross-checked against it. Batch discounts were not verified.
- muse-spark-open pricing and access terms show "contact sales" or limited preview only.

## OpenRouter: free (":free") vision models, free-tier limits, structured outputs, logging/training

### Takeaway
OpenRouter's free tier gives 20 RPM and 50 requests/day on `:free` models, rising to 1,000/day after a lifetime purchase of at least $10 in credits. I could **not** verify any free vision chat model as of Oct 2026 from official pages. The image filter showed only Nemotron embedding models. The `openrouter/free` auto-router is reported to accept images, but that is secondhand and it picks models at random, which makes it unreliable for B. Structured outputs depend on the endpoint. Routing to free models can depend on allowing providers that train on prompts.

### Cited Findings
- Free (`:free`) model limits: 20 requests per minute regardless of credits; 50 requests per day if fewer than 10 credits have ever been purchased, 1,000 per day with at least 10. A negative balance "may see" 402 errors even on free models — [OpenRouter Limits](https://openrouter.ai/docs/api/reference/limits)
- The models page filtered to price 0 and image input showed only `nvidia/nemotron-3.5-embed-1b:free` and `nvidia/nemotron-3.5-embed-8b:free`, both embedding models. Other free models shown (recursive/flint-v1.0:free, baseten/mammoth-1:free, baseten/elephant-1:free, xingchen-agi/xing4.0-29b-a4b:free with 262K ctx) are not described as accepting images — [OpenRouter Models (free + image filter)](https://openrouter.ai/models?max_price=0&input_modalities=image). The page is client-rendered, so this listing may be incomplete.
- Search snippets describe the `openrouter/free` router as picking free models at random and filtering for features such as image understanding, taking text and image input, with a 200K context. The fetched model page itself listed no modalities or context and only showed `response_format`, `tools` and `tool_choice` as accepted fields. It noted the router is not available via EU in-region routing — [openrouter/free](https://openrouter.ai/openrouter/free)
- A third-party reference dated 2026-04-30 lists google/gemma-3-27b-it:free as vision-capable. This is unofficial and was not confirmed for Oct 2026 — [model-capabilities reference](https://czmissioncontrol.duckdns.org/skills/creative/custom-ai-chat-ui/references/model-capabilities.md)
- Structured outputs use `response_format: {type: "json_schema", json_schema: {name, strict, schema}}`. Support is per model and per provider endpoint and changes over time. `provider.require_parameters: true` restricts routing to endpoints that support it. The Response Healing plugin repairs malformed JSON on non-streaming json_schema requests — [OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- OpenRouter does not store prompts or responses by default, only metadata such as tokens and latency, unless you opt in to logging. Opting in to OpenRouter's use of your data earns a 1% discount — [OpenRouter Data Collection](https://openrouter.ai/docs/guides/privacy/data-collection)
- "Separate settings for paid and free models". "If you opt out of training in your account settings, OpenRouter will not route to providers that train." Each provider has its own retention policy, and routing rules do not change based on it — [OpenRouter Provider Logging](https://openrouter.ai/docs/guides/privacy/provider-logging)

### Inferences
- For A, a free text model on OpenRouter is workable: about 20 calls fits the 50/day cap. Model availability and structured-output support are not stable, though, which hurts determinism and reproducibility.
- For B, OpenRouter free is not a dependable route. No free vision LLM was verified, and the random free router gives non-reproducible output quality. A cheap paid OpenRouter vision model would work, but that is outside "free".
- The inputs contain fictional PII, so training exposure is not a legal problem. Even so, free endpoints often need the account's free-model training permission turned on, so assume prompts may be used for training on free routes.

### Gaps
- No authoritative Oct 2026 list of free vision-capable chat models. Fetching the public models API would answer this, but that was not done per the no-API-call constraint.
- Which specific free providers train on or retain prompts was not available on the fetched pages.
- Whether `openrouter/free` honours `json_schema` strict mode is unverified.

## Mistral La Plateforme: free tier, vision models, OCR, structured outputs, training on inputs

### Takeaway
Mistral's current lineup includes several vision-capable models: Mistral Large 4 (v26.10), Medium 3.5 (v26.04), Large 3, and Ministral 3 3B/8B/14B (v25.12). Its dedicated OCR model is OCR 4.1. The free API tier (historically "Experiment", requiring phone verification and no card) has restrictive, unpublished rate limits. Free-tier inputs may be used for training unless you opt out in the Admin privacy settings. Zero Data Retention is available only on pay-as-you-go. Exact per-model prices could not be confirmed from mistral.ai itself.

### Cited Findings
- Models described as multimodal or vision: Mistral Large 4 (v26.10), Mistral Large 3 (v25.12), Mistral Medium 3.5 (v26.04), Ministral 3 14B / 8B / 3B (v25.12, "text and vision") and Z.ai GLM 5.3 Flash. Mistral Small 4 is not described as having vision — [Mistral Models Overview](https://docs.mistral.ai/getting-started/models/models_overview/)
- OCR: OCR 4.1 is current (Premier tier) and provides paragraph-level bounding boxes, block labels and block-level confidence. OCR 3 (v25.12) remains available. mistral-ocr-4-0 was deprecated 9/29/2026 and retired 9/30/2026. mistral-ocr-2505 retired 5/31/2026 and mistral-ocr-2503 retired 12/31/2025 — [Mistral Models Overview](https://docs.mistral.ai/getting-started/models/models_overview/)
- mistral.ai/pricing (as fetched) lists Mistral Large at $0.5/M input and $1.5/M output, a 50% batch discount, and up to 90% off cached input. It says OCR is priced per 1,000 pages but gave the fetcher no rate. The "Free" plan shown there is the consumer and Studio plan — [Mistral Pricing](https://mistral.ai/pricing)
- Secondhand prices: Mistral Medium 3.5 at $1.50/M input and $7.50/M output with about 256–262K ctx — [pricepertoken](https://pricepertoken.com/pricing-page/model/mistral-ai-mistral-medium-3.5), [anotherwrapper](https://anotherwrapper.com/llm-pricing/mistral-medium-3-5). Ministral 3 14B at $0.20/M input and $0.20/M output — [anotherwrapper](https://anotherwrapper.com/llm-pricing/ministral-3-14b-instruct-2512), [pricepertoken](https://pricepertoken.com/pricing-page/model/mistral-ai-ministral-14b-2512). OCR 4.1 at $4 per 1,000 pages standard and $2 per 1,000 via batch — [pasqualepillitteri.it](https://pasqualepillitteri.it/en/news/11041/mistral-ocr-4-1-bounding-boxes-marked-up-pages). OCR 3 was $2 per 1,000 pages — [gend.co](https://www.gend.co/blog/mistral-ocr-3-enhance-document-accuracy-efficiency). None of these were verified on mistral.ai.
- Free API tier: Mistral's help centre (per search snippet; the article URL returned 404 when fetched) says Experiment-plan API requests may be used to train Mistral's models, a verified phone number is required, and no credit card is needed — [search result: help.mistral.ai article 450104](https://help.mistral.ai/en/articles/450104-how-can-i-try-the-api-for-free-with-the-experiment-plan). The docs tier page (docs.mistral.ai/deployment/laplateforme/tier) returned 404 when fetched.
- Free-tier rate limits are not officially published. An aggregator lists 1 request/second, 500K tokens/minute and 1B tokens/month per model. This is unverified — [free-llm-api-resources mirror](https://mintlify.com/cheahjs/free-llm-api-resources/providers/free/mistral-plateforme), [free-llm.com](https://free-llm.com/provider/mistral-ai)
- Training opt-out: the "Anonymous improvement data" toggle under Admin panel > Privacy stops API data being used for improvement. In free mode, Mistral "may use your input and output to train", with opt-out available at any time. ZDR is available only on pay-as-you-go for stateless API calls — [Mistral Help: opt out](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training), [Mistral Help: ZDR](https://help.mistral.ai/en/articles/347612-can-i-activate-zero-data-retention-zdr)
- Structured outputs: the docs recommend custom (schema-enforced) structured outputs as "more reliable". The fetched page did not give `strict` semantics, the list of supported models, or image compatibility — [Mistral Custom Structured Output](https://docs.mistral.ai/capabilities/structured-output/custom_structured_output/)

### Inferences
- Task A: Ministral 3 14B (or 8B) is the cheap fit, at about $0.20/M. Medium 3.5 would be stronger for JA/KO nuance at a cost that is still trivial.
- Task B: Medium 3.5 or Large 4 as a vision LLM with JSON schema, or OCR 4.1 for raw text plus bounding boxes followed by deterministic parsing. OCR 4.1's block-level confidence is useful for flagging low-confidence IDs. One screenshot counts as one page.
- On a free key with 1 RPS, all 31 calls would finish in minutes, but training on inputs is on by default. Turn the toggle off, which matters little here because the PII is fictional.

### Gaps
- Official free-tier RPS/TPM/monthly caps; the docs tier page returned 404.
- Official Mistral per-model prices (Medium 3.5, Ministral 3, Large 4, OCR 4.1); mistral.ai/pricing did not expose them to the fetcher.
- Image token accounting (tokens per 1800x1150 image) for Mistral vision models.
- Whether strict JSON schema is enforced together with image input on Mistral vision models.

## Data retention and training on inputs (summary across providers)

### Takeaway
Groq does not retain inference data by default, keeps reliability and abuse logs for up to 30 days, and offers ZDR to all customers. OpenRouter stores no prompts by default, but free-model routing can require allowing providers that train. Mistral's free tier may train on inputs unless you opt out, and its ZDR is paid-only.

### Cited Findings
- Groq: "By default, Groq does not retain customer data for inference requests." Reliability and abuse logs may contain inputs and outputs and are "retained for up to 30 days". "All customers may enable Zero Data Retention (ZDR) in Data Controls settings" (ZDR disables batch and fine-tuning). Data is stored in GCP buckets in the US. No free-tier-specific differences are stated — [Groq Your Data](https://console.groq.com/docs/your-data)
- Groq training on inputs: the "Your data" page says nothing on the subject. Third-party summaries say the Services Agreement prohibits training on inputs and outputs without permission. This is unverified first-hand — [developersdigest: which APIs train on your data](https://www.developersdigest.tech/blog/which-ai-apis-train-on-your-data), [aireiter](https://aireiter.com/blog/best-free-ai-api)
- OpenRouter: see the OpenRouter section above — [Data Collection](https://openrouter.ai/docs/guides/privacy/data-collection), [Provider Logging](https://openrouter.ai/docs/guides/privacy/provider-logging)
- Mistral: see the Mistral section above — [opt-out](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training)

### Inferences
- With fictional PII, the privacy-preferred order is Groq (no default retention, optional ZDR), then OpenRouter paid or non-training endpoints, then Mistral free with the opt-out toggled, then OpenRouter free and training-permitted endpoints.

### Gaps
- No first-hand text of Groq's Services Agreement training clause was retrieved.

## Reliability caveats

### Takeaway
Model churn on Groq was heavy in 2026: four vision or text model families were retired between March and September. The only Groq vision model is a preview model. OpenRouter free models change and route at random. Mistral also retired OCR versions quickly.

### Cited Findings
- Groq: preview models "may be discontinued at short notice" — [Groq Models](https://console.groq.com/docs/models). Llama 4 Scout and Maverick, qwen3-32b, qwen3.6-27b, Llama 3.x and compound were all retired during 2026 — [Groq Deprecations](https://console.groq.com/docs/deprecations)
- Groq best-effort JSON mode "occasional 400 errors can occur". Strict mode is incompatible with streaming and tool use — [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)
- Groq 429 handling uses `retry-after`, and limits are per organization — [Groq Rate Limits](https://console.groq.com/docs/rate-limits)
- OpenRouter: structured-output support "can change over time" per endpoint. A negative balance gives 402 even on free models — [Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [Limits](https://openrouter.ai/docs/api/reference/limits)
- Mistral: mistral-ocr-4-0 lasted less than a month before retiring on 9/30/2026 — [Mistral Models Overview](https://docs.mistral.ai/getting-started/models/models_overview/)

### Inferences
- For a reproducible batch pipeline, cache all B outputs to disk (the repo already has code/cache/image_facts.json and ocr_raw). Pin model IDs, handle 429 and 400 errors with retry plus schema validation, and keep a deterministic fallback for A.

### Gaps
- No published uptime or SLA figures for any of these free tiers were found.

## Estimated cost: about 20 text calls (300 in / 50 out) plus 11 image calls (about 2,000 out each)

### Takeaway
On every provider the total is well under $0.25 at paid list prices, and $0 on the free tiers within their limits. The best per-provider picks are Groq gpt-oss-120b (A) plus qwen3.8-27b (B) at about $0.11; Mistral Ministral 3 14B (A) plus Medium 3.5 (B) at about $0.21, or with B on Ministral 14B or OCR 4.1 about $0.01–$0.05; and OpenRouter free at $0, though no free vision model was verified.

### Cited Findings
- Price inputs: gpt-oss-120b $0.15/$0.60; gpt-oss-20b $0.075/$0.30; qwen3.8-27b $0.80/$4.00, 2,048 tokens per image — [Groq Models](https://console.groq.com/docs/models), [Groq Vision](https://console.groq.com/docs/vision). Mistral Medium 3.5 $1.50/$7.50 and Ministral 3 14B $0.20/$0.20 (secondhand) — [pricepertoken](https://pricepertoken.com/pricing-page/model/mistral-ai-mistral-medium-3.5), [anotherwrapper](https://anotherwrapper.com/llm-pricing/ministral-3-14b-instruct-2512). OCR 4.1 $4 per 1,000 pages (secondhand) — [pasqualepillitteri.it](https://pasqualepillitteri.it/en/news/11041/mistral-ocr-4-1-bounding-boxes-marked-up-pages). OpenRouter `:free` costs $0 within 50 RPD — [OpenRouter Limits](https://openrouter.ai/docs/api/reference/limits)

### Inferences (my arithmetic; assumptions stated)
- Task A totals are 6,000 input and 1,000 visible output tokens. Assume reasoning models add about 250 hidden output tokens per call, for about 6,000 output tokens in total.
  - Groq gpt-oss-120b: 6,000 × $0.15/M + 6,000 × $0.60/M ≈ **$0.0045**. Without reasoning overhead it is about $0.0015.
  - Groq gpt-oss-20b: about **$0.0023**.
  - Mistral Ministral 3 14B: 7,000 × $0.20/M ≈ **$0.0014**.
- Task B assumes about 2,550 input tokens per call (2,048 image plus about 500 prompt and schema) and 2,000 output, giving about 28K input and 22K output in total.
  - Groq qwen3.8-27b: 28K × $0.80/M + 22K × $4.00/M ≈ $0.022 + $0.088 = **about $0.11**. Tiling into 3 crops per request roughly doubles input, to about $0.15 total.
  - Mistral Medium 3.5: Mistral image token counts are unknown, so assume about 3,000 input per call. 33K × $1.50/M + 22K × $7.50/M ≈ $0.05 + $0.165 = **about $0.21**.
  - Mistral Ministral 3 14B: 55K × $0.20/M ≈ **$0.011**.
  - Mistral OCR 4.1: 11 pages × $4/1,000 ≈ **$0.044**, plus a cheap LLM pass to map the text into JSON.
- **Grand totals:** Groq about $0.11–$0.16; Mistral about $0.012 (all Ministral) to about $0.21 (Medium 3.5 for B); OpenRouter free $0 for A, with no verified free option for B. On the free tiers of Groq and Mistral the run costs $0. The Groq free 8K TPM caps B at about 1 call per minute (about 11–15 minutes total), well within 200K TPD.

### Gaps
- Exact image tokenization for Mistral and OpenRouter vision models, so the B input estimates for them are assumptions.
- Reasoning-token overhead for gpt-oss and qwen3.8 is workload-dependent and not documented as a fixed number.

# AE-32C E.6 — OpenRouter Nemotron Free Model Preflight

**Status:** Proposed implementation; not yet validated by G9.42 or live preflight.

## Decision

Set the active OpenRouter default to `nvidia/nemotron-3.5-lightning:free`.

The previous E.5 batch used `deepseek/deepseek-v4.1-flash-1017` and all four OpenRouter graph trials stopped at HTTP 402 with zero completion tokens. The run evidence identifies a provider API error but does not include the raw upstream message, so billing, model-route entitlement, or account policy must not be asserted as the definitive cause. The replacement is a controlled provider/model change to test whether a free endpoint is available to the account.

OpenRouter's current model page documents chat completions and tool calling for Nemotron 3.5 Lightning Free, but does not list `response_format` support. Therefore:

- The model is not added to `OPENROUTER_JSON_OBJECT_MODELS`.
- `get_capabilities()["json_object_mode"]` remains false for this model.
- The investigator must use ordinary chat, then enforce the existing strict local JSON parser and action-schema validator.
- Direct calls to `chat_structured()` fail closed for models without verified JSON-object support.
- No evidence, citation, action-schema, or completion acceptance rules are relaxed.

OpenRouter lists this free endpoint as rate-limited and currently unavailable through EU in-region routing. Its model page also carries a provider data-use notice. Review current account routing and data-handling terms before sending non-public or confidential source material.

## Cloudflare decision

Do not change Cloudflare's active model in this increment. E.5 run 42891184108 recorded 4/4 baseline completions and four graph investigations attempted, with no Cloudflare provider API failures. The two unsuccessful graph outcomes were finalization-recovery exhaustion and a direct-source-witness gap. Those observations do not establish that the Cloudflare model prevented the test from running.

Keep `@cf/meta/llama-3.1-8b-instruct-fast` for this isolated OpenRouter change. A separate Cloudflare Qwen experiment may be considered only after a model-specific preflight confirms the required request mode and action schema. Cloudflare documents function calling and reasoning for `@cf/qwen/qwen3.8-27b`, but its published JSON Mode supported-model list does not currently list that Qwen model; do not assume it is a drop-in JSON-mode replacement.

## Preflight acceptance

The provider-only preflight must verify:

1. OpenRouter transport returns non-empty content.
2. The model emits a strict JSON action object over ordinary chat.
3. The local parser rejects duplicate keys and non-standard JSON constants.
4. The action object has exactly `action`, `tool`, `arguments`, and `reason` with the required `tool_call` shape.
5. No raw model response or credential is written to the report.

The preflight does not execute repository tools or prove investigation quality. After it passes, rerun G9.42 on the exact changed Stage1 commit before any new live round-robin batch.

## Sources

- OpenRouter model page: https://openrouter.ai/nvidia/nemotron-3.5-lightning:free
- Cloudflare Qwen 3.8 27B model page: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Cloudflare JSON Mode supported-model list: https://developers.cloudflare.com/workers-ai/features/json-mode/

# AE-32C E.7-R.3N — Endpoint-aware provider-independent response negotiation

**State:** corrective implementation and offline validation; NOT G9.42 accepted or live-provider verified.  
**Target branch:** `stage1/section-uuids`. **Reference source:** supplied 12 November 2026 development-branch ZIP.  
**Supersedes (do not upload separately):** E.7-R.3 Provider-Independent Response Bridge.

## Goal and trust boundary

Changing the LLM should not require changing AE-32C's investigator, evidence engine, or validation architecture. Providers remain responsible for credentials, endpoint routing and untrusted response envelopes; the shared response normalizer reduces supported representations to the **same canonical action**; deterministic AE-32C code alone authorizes actions and validates evidence, provenance, cost, source ranges, and final diagnoses.

Supported response transports are **optional**, not mandatory: strict JSON Schema, one inert virtual response function, JSON-object mode, strict JSON text, fenced/unambiguous embedded JSON, explicit fielded text. Arbitrary prose is never guessed into a repository action. Native tool calls are data; the function is never executed.

## Strategy policy

**OpenRouter** (optional endpoint discovery via a read-only metadata request):

1. A serving endpoint explicitly advertises `structured_outputs` → request strict `json_schema` with `provider.require_parameters=true`.
2. Otherwise an endpoint explicitly advertises `tools` → request one inert `submit_ae32c_response` function with `tool_choice=auto`, `parallel_tool_calls=false`, and `provider.require_parameters=true`.
3. Otherwise an endpoint explicitly advertises `response_format` → request `json_object` with `provider.require_parameters=true`.
4. Otherwise → unconstrained ordinary chat and deterministic plain-text normalization.

OpenRouter routing can select different serving endpoints for the same model; metadata support is a **hint**, not proof that a schema was honored. `require_parameters` makes the provider reject a request instead of silently ignoring unsupported structured-output parameters. AE-32C still validates every action. If endpoint metadata is absent, stale, invalid, or unavailable while discovery is enabled, select ordinary text. If discovery is disabled, preserve the existing reviewed exact-model JSON-object allowlist; no new capability is guessed from a model family.

**Cloudflare Qwen** continues to use optional Chat Completions native function calling (one virtual function, `tool_choice=auto`) with an independently budgeted text fallback. It does not depend on OpenRouter metadata, response healing, or OpenRouter routing.

**NaraRouter** retains its bounded chat and locally validated action-normalization path. Its malformed response envelopes remain failures.

## Portable wire schema versus local action schema

The provider wire schema contains exactly one required string field, `action_json`, and `additionalProperties: false`. `action_json` is a serialized canonical AE-32C action (`tool_call` or `final`). This avoids forcing a provider to implement AE-32C's changing nested evidence-tool schemas in its strict JSON schema subset. The normalizer decodes the nested JSON with duplicate-key and non-finite-value rejection. The existing action, source, evidence, and diagnosis validators remain **authoritative**. A raw canonical response is still permitted when the provider cannot enforce a wire schema.

The same portable schema is used for JSON Schema and tool-call arguments, so provider choice does not change the investigator's internal protocol.

## Discovery, cache and privacy

Optional environment configuration:

```text
FEA_OPENROUTER_CAPABILITY_DISCOVERY=1
FEA_OPENROUTER_RESPONSE_HEALING=1
```

Discovery is **opt-in** and defaults to off. When enabled it fetches `GET https://openrouter.ai/api/v1/models/{author}/{slug}/endpoints` for the **configured** OpenRouter model. This is a fixed HTTPS origin, with strict model-ID validation, disabled redirects, a maximum 6-second request timeout, a 128-KB bounded JSON result, and a memory-only 300-second TTL. It transmits authorization and the model identifier, **not repository text**. Network, metadata, parse and identity mismatches all fail closed. No untrusted metadata string is copied into the model prompt.

OpenRouter response healing is separately **opt-in** (defaults off) and is sent only with JSON Schema or JSON-object requests, not tool calls or ordinary chat. It is a provider-side syntax aid, not schema validation or causal verification. Consult the account privacy/retention configuration before enabling it.

## Request rejection and fallback

If a current **structured** inference request was actually attempted and failed, the investigator may authorize **one** additional text-only inference after separately reserving prompt, token and estimated cost budget. It does **not** retry transport failures, authentication failures, rate limits, quota exhaustion, or provider-internal errors. HTTP 400/415/422 remain eligible only in structured mode, subject to the existing safe error-classification checks. OpenRouter HTTP 404 is eligible **only** when safe structural diagnostics specifically classify the rejection as `required_parameters_no_endpoint` for a structured request, never a generic 404, a missing model, or a regional restriction. An HTTP 200 malformed completion or truncated output is never converted into a success.

If response format is rejected but plain text works, the same AE-32C normalizer handles the fallback; no extra repository tool is executed by a preflight.

## Provider-only preflight

OpenRouter preflight runs ordinary connectivity, one negotiated inert-action request, and one explicit text normalization request. The negotiated mode and metadata source are reported without logging provider payload bodies. The native response function returns *data only*. Existing Cloudflare native/text probes are unchanged, and G9.42 remains strictly offline.

## Scope / intentionally deferred

- No automatic remote file edits, commits, pushes, or patch application.
- No live API requests in package preparation; the user controls GitHub validation and provider preflight.
- No cross-provider inference until exact-commit G9.42 passes and each provider preflight establishes a usable response mode.
- No arbitrary prose-to-command semantic interpreter, provider-side action execution, or automatic weakening of evidence policy.
- No benchmark claims about causal accuracy or superiority of one provider from these offline protocol tests.
- No global provider capability cache shared between accounts; per-instance cache keys are limited to the fixed OpenRouter API origin plus exact model ID.

## Evidence and references

- OpenRouter endpoint list API: https://openrouter.ai/docs/api/api-reference/endpoints/list-endpoints
- OpenRouter November 10, 2026 structured-output guide: https://openrouter.ai/blog/structured-output-llm/
- OpenRouter model supported parameters: https://openrouter.ai/docs/api/api-reference/models/get-models
- OpenRouter Response Healing: https://openrouter.ai/docs/guides/features/plugins/overview
- Cloudflare Qwen model: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/

The supplied 12 November ZIP files do not include Git history, so archive content equivalence is established through byte comparisons, not a new remote-HEAD assertion. The historical logs report validation run `43171307418` at source commit `028d35d451a2aee3611cb08e617095bfb0dc9029`; that result **does not validate this corrective package**.

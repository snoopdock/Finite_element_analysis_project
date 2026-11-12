# AE-32C E.7-R.2 — Cloudflare Qwen native response tool

## E.7-R.2.1 corrective amendment — named function choice and diagnostics

Target model: `@cf/qwen/qwen3.8-27b`

Validated source baseline before this correction:
- Branch: `stage1/section-uuids`
- Commit: `4bd0d76cdd64bbe108ea4b0da2090f0942305199`
- G9.42 validation run: `43160990788` (passed)
- Qwen provider preflight run: `43161366696` (native function-call request failed with HTTP 400)

### Observed failure

The transport/sentinel probe succeeded. The subsequent native response-tool request returned HTTP 400 in approximately 0.205 seconds. No tool-call response was returned and no repository tool was executed.

The uploaded preflight artifact intentionally omitted the upstream error body. Therefore, the exact Cloudflare validation message is unavailable and the original 400 cannot be attributed conclusively to one request field.

The prior E.7-R.2 adapter transformed the OpenAI-style function definition into the legacy flat `{name, description, parameters}` form and omitted `tool_choice`. That was a divergence from Cloudflare's maintained Workers AI SDK request preparation, which maps tools to the OpenAI-style `{type: "function", function: {...}}` representation and uses a named-function `tool_choice` when one specific function must be forced.

### Corrected request contract

The Qwen response-tool path continues to use the direct Workers AI REST endpoint:

`POST /accounts/{account_id}/ai/run/@cf/qwen/qwen3.8-27b`

The request now sends:

- The original OpenAI-style function tool definition.
- `tool_choice: {"type":"function","function":{"name":"submit_ae32c_response"}}`.
- `parallel_tool_calls: false`.
- `max_completion_tokens` using the existing bounded token allowance.
- No `response_format` or JSON Mode request.

The named tool choice is important: Cloudflare's maintained SDK maps a forced single-tool selection to the named-function form rather than the weaker generic `required` value. The virtual function is a response envelope only; it is never executed.

### Response parsing

The adapter accepts the documented Workers AI flat response form (`result.tool_calls[]` with `name` and `arguments`) and the OpenAI-compatible form (`choices[0].message.tool_calls[]` with `function.name` and `function.arguments`).

It requires exactly one returned call, strictly parses string arguments with duplicate-key and non-standard-constant rejection, and returns a `ProviderToolCall` data object. The AE-32C response normalizer and investigator remain responsible for canonical action validation, evidence checks, permission checks and finalization restrictions. The native-response integration fixture now also declares Qwen JSON-object mode as unsupported, matching the production model capability declaration.

### Safe diagnostics

For HTTP errors, the adapter now retains only:
- HTTP status.
- A bounded error category.
- Up to five numeric Cloudflare error codes.
- A validated `cf-ray` / request identifier.

It never stores or prints the provider-controlled error message/body. Native-tool failure counters are incremented on HTTP rejection, transport failure, malformed response and missing/invalid tool-call cases.

### Scope deliberately unchanged

- No model default or provider routing change.
- No JSON Mode enablement for Qwen.
- No evidence-tool execution during preflight.
- No action permission, evidence acceptance or finalization changes.
- No retry-count or token-budget increase.
- No repository investigation in the provider preflight.

### Acceptance

1. Run G9.42 against the new Stage1 commit.
2. Run provider-only Cloudflare preflight for `@cf/qwen/qwen3.8-27b`.
3. Require `native_tool_call_probe.status == "passed"`, one expected function call, canonical action schema validity, and `tool_executed == false`.
4. If HTTP rejection recurs, inspect only the new safe error category, numeric error code and request ID; do not log the raw provider body.
5. Only after preflight passes, run one bounded Qwen investigation.

### Research references

- Qwen 3.8 27B model page: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Workers AI OpenAI-compatible endpoints: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- Cloudflare maintained Workers AI provider tool mapping: https://github.com/cloudflare/ai/blob/main/packages/workers-ai-provider/src/utils.ts
- Cloudflare issue demonstrating named function tool choice on `/ai/run`: https://github.com/cloudflare/ai/issues/574
- Cloudflare traditional function calling: https://developers.cloudflare.com/workers-ai/features/function-calling/traditional/

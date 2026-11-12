# AE-32C E.7-R.2.2 — Cloudflare Qwen Chat Completions correction

Target branch: `stage1/section-uuids`

## 1. Evidence and exact failure

- G9.42 validation run: `43166265806`
- G9.42 validated source commit: `1558f352c7a98929f6c3102e3d4013e202c19771`
- G9.42 result: 3,291 passed, 8 skipped, 0 failed (3,299 total)
- G9.42 targeted selection: 263 passed, 0 failed
- Validation-engine tests: 51/51 passed
- Provider preflight run: `43166952159`
- Requested/effective model: `@cf/qwen/qwen3.8-27b`
- Preflight result: `native_tool_call_compatibility_failed`
- Baseline transport: HTTP 200; sentinel matched
- Native function call: HTTP 400; Cloudflare numeric error code `8007`
- Cloudflare request identifier: `a59368dd396b54a3-MSP`
- Repository tools executed by preflight: 0

The raw provider error body was intentionally omitted from the uploaded artifacts. The numeric code and request ID are available, but the exact provider message is not.

## 2. Root-cause assessment

The previous implementation sent the native response-tool request to:

`POST /accounts/{account_id}/ai/run/{model}`

but constructed a body containing Chat Completions-oriented fields:

- `max_completion_tokens`
- `parallel_tool_calls`
- named-function `tool_choice`
- OpenAI-style `tools`

The direct `/ai/run/{model}` route and the OpenAI-compatible Chat Completions route are distinct API contracts. Cloudflare's Qwen model documentation explicitly lists the OpenAI-compatible Chat Completions endpoint and its tool/function parameters. Cloudflare's OpenAI compatibility guide gives the route:

`POST /accounts/{account_id}/ai/v1/chat/completions`

and uses a request body containing `model` and `messages`.

The most defensible correction is to send the native Qwen response-tool call through the documented Chat Completions route, rather than continue mixing request fields across the two APIs.

### Important qualification about error 8007

Cloudflare's current public Workers AI error catalogue does not list code `8007`. A separate Cloudflare documentation issue records that code in a Batch API/request-queue context ("This model does not support request queuing"). That is not enough to assert that the synchronous preflight's 8007 had the same meaning. This package therefore does not hard-code a queue interpretation. It preserves the numeric code and request identifier and fixes the independently verifiable endpoint/request-contract mismatch.

## 3. Changes in this package

### `providers/cloudflare.py`

1. Adds a dedicated OpenAI-compatible Chat Completions path:
   `POST /accounts/{account_id}/ai/v1/chat/completions`.
2. Adds `model` to the Chat Completions request body.
3. Uses `max_completion_tokens` only on the Chat Completions path.
4. Sets `stream: false` for deterministic, non-streaming preflight and response parsing.
5. Sends `tools`, the named-function `tool_choice`, and `parallel_tool_calls: false` on this endpoint.
6. Routes Qwen's `chat_with_response_tool` through the Chat Completions path.
7. Adds `chat_openai_compatible` so the Qwen baseline transport probe checks the same endpoint family before attempting the function call.
8. Leaves ordinary Cloudflare chat on `/ai/run/{model}` with its existing `max_tokens` contract.
9. Extends safe error parsing to support both Cloudflare's `{errors:[...]}` and OpenAI-compatible `{error:{...}}` error envelopes. It still never logs provider-controlled raw error messages or credentials.

### `provider_preflight.py`

1. For Qwen, the baseline connectivity probe uses Chat Completions rather than `/ai/run`.
2. The native response-tool probe uses the same endpoint.
3. Uses a bounded `max_completion_tokens` allowance of 2,048 for the forced tool-call probe. This leaves room for reasoning plus the required tool-call envelope; it is not an unlimited completion.
4. Keeps the two-logical-call preflight bound.
5. Records the exact endpoint mode and completion-token cap in the JSON and Markdown artifacts.
6. Does not execute repository tools.

### Regression tests

- Verify the Qwen native response tool uses `/ai/v1/chat/completions`.
- Verify the request includes `model`, `messages`, `tools`, named `tool_choice`, `parallel_tool_calls: false`, `stream: false`, and `max_completion_tokens`.
- Verify ordinary Cloudflare chat still uses `/ai/run/{model}` and `max_tokens`.
- Verify both Chat Completions response envelopes and OpenAI-style error envelopes.
- Verify safe numeric error code/request-ID reporting without raw message leakage.
- Verify Qwen preflight checks Chat Completions transport first and does not attempt the native call if that endpoint check fails.
- Verify the preflight remains bounded and no repository tool is executed.

## 4. External documentation and research

1. Cloudflare Qwen 3.8 27B model page:
   https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
   Documents Qwen's function-calling capability, OpenAI-compatible Chat Completions support, `tools`, `tool_choice`, `parallel_tool_calls`, and `max_completion_tokens`.

2. Cloudflare OpenAI-compatible API endpoints:
   https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
   Documents the `/ai/v1/chat/completions` endpoint and the account-scoped base URL.

3. Cloudflare Workers AI provider issue #560:
   https://github.com/cloudflare/ai/issues/560
   Documents named-function `tool_choice` enforcement and notes that reasoning models require sufficient completion tokens for both reasoning and the tool-call envelope. This informed the bounded 2,048-token preflight cap; it does not establish a meaning for error 8007.

4. Cloudflare Workers AI error catalogue:
   https://developers.cloudflare.com/workers-ai/platform/errors/
   The current published catalogue does not list code 8007.

5. Separate Batch API issue mentioning 8007:
   https://github.com/cloudflare/cloudflare-docs/issues/21718
   This issue associates 8007 with unsupported request queuing in a batch context. Because the AE-32C request was a synchronous model call, this package does not treat that issue as a confirmed diagnosis.

6. Qwen low-reasoning JSON-schema timeout issue:
   https://github.com/cloudflare/workers-sdk/issues/16165
   Reports a model-specific timeout for `response_format: json_schema` with `reasoning_effort: low`. This package does not use JSON Schema mode or set `reasoning_effort`; it uses a function call on the Chat Completions endpoint.

## 5. Verification

Against the reconstructed Stage1 source corresponding to validated commit `1558f352c7a98929f6c3102e3d4013e202c19771`, with the two previous E.7-R.2 packages applied to the supplied `75f7d0bb` source archive:

- Focused Cloudflare/native-tool/preflight/investigator integration tests: **36 passed**.
- Reconstructed G9.42 targeted selection plus the new Cloudflare native-tool and integration modules: **279 passed**.
- Python syntax compilation: passed.

A full repository regression was attempted locally but the execution environment interrupted the process at its 60-second automatic limit. This package is therefore **not** claiming a new full-regression pass or a new G9.42 validation. The previously uploaded G9.42 run remains passed for the unmodified baseline commit `1558f...`.

No live Cloudflare request was made during package construction. A live preflight is still required to establish that the corrected endpoint works with the user's Cloudflare account and Qwen deployment.

## 6. Upload

Replace these four files:

- `providers/cloudflare.py`
- `audit_engine/semantic_audit/ae32c/provider_preflight.py`
- `tests/test_cloudflare_native_tool_calls.py`
- `tests/semantic_audit/test_ae32c_patch4_incident_evaluation.py`

Add this file:

- `docs/audit-engine/AE-32C-E7R2-2-Cloudflare-Qwen-Chat-Completions-Correction.md`

Suggested commit:

`AE-32C E.7-R.2.2: route Qwen native response calls through Chat Completions`

Do not modify `main`.

## 7. Next gate

1. Upload these files to `stage1/section-uuids`.
2. Run G9.42 against the exact new commit.
3. Only after G9.42 passes, run the bounded Cloudflare Qwen preflight.
4. Require both `transport_probe.status = completed` and `native_tool_call_probe.status = passed`.
5. If it fails, preserve the new error code, error category, endpoint mode and request ID. Do not retry blindly or change the model default.

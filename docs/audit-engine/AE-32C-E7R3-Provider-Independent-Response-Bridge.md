# AE-32C E.7-R.3 — Provider-Independent Response Bridge

**Target branch:** `stage1/section-uuids`  
**Source baseline:** `028d35d451a2aee3611cb08e617095bfb0dc9029`  
**Package:** `AE32C_E7R3_Provider_Independent_Response_Bridge` (historical bridge; superseded by the E.7-R.3N extension, see `AE-32C-E7R3N-Endpoint-Capability-Negotiation.md`)

## Purpose

AE-32C must not require an LLM or provider to support API-enforced JSON mode or native function calling. Those features are optional response transports. The investigation engine needs one canonical internal action contract and a local, deterministic normalizer that can consume multiple model response representations.

The model proposes a response. AE-32C validates it. The model never executes repository tools.

## Response representations

The normalizer accepts:

1. Canonical JSON text.
2. A single JSON object inside one Markdown JSON fence.
3. One unambiguous embedded JSON object.
4. The explicit labelled tool-call text envelope.
5. The explicit fielded final-diagnosis text envelope.
6. The virtual `submit_ae32c_response` native function call.
7. The provider-neutral `ProviderResponse` envelope carrying text and/or a native response call.

The tool-call text envelope can use ordinary `key: value` argument lines (not JSON). The fielded final text envelope is line-oriented and does not require JSON mode. It uses explicit labels for summary, root-cause statement/confidence/evidence IDs, source-reference tuples, claim blocks, corrective action, limitations, and next steps.

### Important boundary

This is not arbitrary natural-language command execution. Unlabelled prose is not guessed into an action. A deterministic parser cannot reliably infer an exact tool name, arguments, evidence IDs, source line, or hash from unconstrained prose. If a model returns unlabelled prose, AE-32C rejects it and uses the existing bounded recovery path. A future semantic-interpretation stage would need separate threat modelling, cost limits, and evaluation; it is not part of this package.

## Architecture

- `providers/base.py` defines `ProviderResponse`, a provider-neutral envelope, and the optional `chat_text` compatibility method.
- `providers/capabilities.py` declares plain-text mode whenever the adapter has a chat entry point. JSON and native tool support remain explicit, optional capabilities.
- Provider adapters own transport details only. Cloudflare's `chat_text` uses its OpenAI-compatible Chat Completions endpoint; the shared OpenAI-compatible adapter uses ordinary chat.
- `response_normalizer.py` converts accepted representations to the same canonical action payload.
- `investigator.py` remains authoritative for tool allowlists, argument schemas, evidence IDs, source references, budgets, finalization, and no-tool finalization.
- The virtual response function is data only. It is never executed and does not grant repository access.

## Native-mode fallback

When the investigator chooses native response-tool mode and the provider rejects that structured request, it may make one bounded plain-text request if all of these conditions hold:

- The native response produced no usable response.
- The adapter reports a current HTTP attempt for that native request.
- The current HTTP status is a non-transient request rejection (`400`, `415`, or `422`).
- The adapter telemetry does not classify the error as authentication/permission, quota/rate-limit, transport, or provider-internal failure.
- Plain-text chat is available.
- A second prompt/token/cost reservation succeeds.

The fallback uses no `tools`, `tool_choice`, or `response_format` parameter. It asks for canonical JSON text or the explicit labelled text contract and passes the response through the same local normalizer and investigator validators.

HTTP error `8007` remains an observed provider code. This package does not assign it an undocumented meaning. The fallback decision is based on the current request's HTTP status and safe adapter telemetry, not on an interpretation of `8007`.

## Qwen-specific compatibility posture

For Cloudflare Qwen 3.8 27B, native function calling remains an optional first attempt. The request uses `tool_choice: "auto"` with exactly one virtual response function. This avoids forcing a named function while Qwen thinking mode is enabled. If the request is rejected, the investigator can use the plain-text path.

Cloudflare's published model documentation exposes tools and `tool_choice` for the Qwen model; Cloudflare also documents the OpenAI-compatible Chat Completions endpoint. These published capabilities do not guarantee behavior for every account/model deployment. Live preflight remains mandatory.

References:
- Cloudflare Qwen 3.8 27B model documentation: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Cloudflare function calling: https://developers.cloudflare.com/workers-ai/features/function-calling/
- Cloudflare OpenAI-compatible endpoints: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- Qwen function-calling and thinking-mode tool-choice guidance: https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling

## Provider preflight v2

The provider-only preflight now distinguishes:

- baseline transport,
- optional native response-tool probe,
- optional API-enforced/local JSON action probe,
- provider-independent plain-text envelope probe.

A provider is usable if at least one response mode normalizes to a valid canonical action. A native tool-call failure is retained in the report but does not fail preflight when the plain-text path passes. No repository evidence tool is executed by preflight.

Cloudflare Qwen performs baseline transport, native tool-call probe, and a plain-text envelope probe whose `search_repository` arguments are supplied as `key: value` lines rather than JSON. OpenRouter and other Cloudflare models test JSON action mode where applicable plus plain text. NaraRouter now tests the same plain-text envelope after transport.

## Security and correctness invariants

- No unlabelled prose is interpreted as a tool action.
- Native calls must use exactly `submit_ae32c_response`.
- Multiple native calls and mixed text-plus-native-call envelopes are rejected as ambiguous.
- Duplicate JSON keys, malformed source-reference tuples, invalid evidence IDs, unknown labels, and malformed claim blocks are rejected.
- No provider-supplied tool is executed.
- Every proposed action is revalidated against the registered tool catalog and current investigation state.
- Evidence, provenance, permissions, finalization, and diagnosis validation remain unchanged.
- Fallback is bounded by the same investigation call, token, prompt-size, elapsed-time, and cost budgets.

## Historical E.7-R.3 bridge validation (not the superseding E.7-R.3N package)

- G9.42 target profile: **311 passed**.
- Focused provider/response bridge suite: **134 passed**.
- Python syntax compilation: passed.
- Patch application against the supplied Stage1 archive: checked separately in the package build.
- Full repository regression: attempted locally but interrupted by the execution environment's 60-second automatic execution limit. No full-regression pass is claimed.
- Live Cloudflare Qwen request: **not performed**. The user must run the provider-only preflight after upload.

## Release gate

After manual upload to `stage1/section-uuids`:

1. Run G9.42 against the exact new commit.
2. Require targeted, full regression, validation-engine, provenance, and evidence-catalog checks to pass.
3. Run the Cloudflare Qwen provider-only preflight.
4. Confirm either `native_tool_call` or `plain_text_envelope` is listed in `usable_response_modes`.
5. Only then run one controlled Qwen repository investigation.
6. Do not restart cross-provider round-robin evaluation until the same canonical response tests pass for each selected provider/model.

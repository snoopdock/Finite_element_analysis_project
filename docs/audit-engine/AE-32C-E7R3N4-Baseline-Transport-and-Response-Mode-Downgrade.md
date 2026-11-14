# AE-32C E.7-R.3N.4 — Baseline Transport Parity and Session Response-Mode Downgrade

## Status

- Target branch: `stage1/section-uuids`
- Reconstructed baseline commit reported by the uploaded GitHub evidence: `c6366a4a8feff424dbd7de5b94805af6158e6577`
- Prior G9.42 validation: run `43573054190` (passed)
- Prior Cloudflare provider preflight: run `43573263045` (passed)
- Prior live evaluation: run `43573277918` (incomplete; see evidence record)
- This change: locally tested; new GitHub G9.42 and live-provider acceptance are pending.

## Problem established by the logs and source inspection

The live evaluation used different Cloudflare adapter entry points for its two conditions:

- Baseline called `provider.chat()`. In the supplied Cloudflare adapter, that is the Workers AI `/ai/run/{model}` path.
- Graph-assisted native response calls used `chat_with_response_tool()`, which uses the OpenAI-compatible `/ai/v1/chat/completions` path.
- The successful plain-text preflight also used the OpenAI-compatible Chat Completions path.

The baseline failed with a 45-second read timeout on each of two attempts (about 100 seconds elapsed), while the preflight made successful HTTP 200 requests through Chat Completions. The conditions therefore did not share the same transport family.

Separately, the preflight proved that a single native response and a single labelled-text response could be normalized. It did not prove that the model would honor the native envelope over a multi-turn investigation. The live investigation returned HTTP-successful but invalid response shapes, including `native_tool_action_fields_invalid`, `tool_action_shape_invalid`, `native_tool_envelope_shape_invalid`, and `unexpected_native_tool_name`. The investigator kept selecting native mode on subsequent turns and exhausted its response-recovery budget.

## Corrections

### 1. Baseline transport parity

`live_evaluation.py` now prefers the provider adapter's explicit `chat_text()` interface for the baseline and falls back to legacy `chat()` only when `chat_text()` is unavailable. For the Cloudflare adapter in this branch, `chat_text()` uses the same `/ai/v1/chat/completions` endpoint family as native response-tool calls, but sends no tools or response-format constraint.

The selected interface is recorded in the comparison artifact. The adapter's reported endpoint mode is also recorded when available. This makes the transport choice auditable.

This establishes endpoint-family parity, not identical request payloads or equal total compute. The baseline remains a single no-tool response; graph-assisted investigation remains multi-turn and tool-enabled. The comparison artifact continues to state that diagnostic accuracy and graph benefit require independent review.

### 2. One-way structured-to-text downgrade

The investigator now records the response mode used for each provider call. If a structured mode (`json_schema`, `native_tool_call`, or `json_object`) returns an HTTP-successful response that fails deterministic response normalization or the top-level tool-action shape check, the investigator may downgrade the remainder of that investigation to `plain_text` exactly once.

The rejected response is not dispatched. The next ordinary model turn receives the explicit provider-independent text response contract and remains subject to the existing round, prompt, token, time, cost, action, evidence, and citation constraints. No extra same-turn model call is created by this model-output fallback.

Transport-level structured-request fallback is also made persistent for the rest of the investigation after the existing safe fallback policy authorizes it. This avoids retrying the same rejected structured mode on every later turn.

### 3. Auditable response-mode diagnostics

Investigation reports now include:

- initial response mode;
- last response mode;
- session override;
- whether the one-way plain-text downgrade was used;
- last adapter-reported endpoint mode, when available.

The comparison summary and Markdown render these fields alongside the baseline's selected text interface and endpoint mode.

## Safety and acceptance boundaries

- The virtual response function remains data-only; it is never executed.
- Malformed native calls, malformed JSON, ambiguous prose, invalid action envelopes, and unregistered tool names remain rejected.
- Plain-text normalization is deterministic and does not infer actions from arbitrary prose.
- The investigator remains the only authority that validates actions and dispatches read-only evidence tools.
- Evidence references, source hashes, direct citations, diagnosis validation, and finalization gates are unchanged.
- This package does not claim that Qwen will complete an investigation or produce a causally correct diagnosis.

## External technical references

1. Cloudflare's Qwen 3.8 27B model page lists function calling and reasoning support, documents OpenAI-compatible Chat Completions, and lists `max_completion_tokens`, `tools`, and `tool_choice` request parameters: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
2. Cloudflare's OpenAI compatibility guide documents the Workers AI Chat Completions endpoint at `/ai/v1/chat/completions`: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/

These references establish available API interfaces and documented capabilities. They do not guarantee latency, endpoint availability, or consistent multi-turn adherence by a particular model deployment.

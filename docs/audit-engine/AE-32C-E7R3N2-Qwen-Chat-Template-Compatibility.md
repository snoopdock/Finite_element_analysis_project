# AE-32C E.7-R.3N.2 — Qwen chat-template message compatibility

**Branch:** `stage1/section-uuids` only. **Change type:** narrow provider-boundary corrective patch. **Release status:** offline tested; requires new exact-commit G9.42 validation and live Cloudflare preflight.

## Observed evidence

The G9.42 run `43485894877` accepted source commit `f0fd654a316ba3fae2225621f367c214b79cd5c5`: 331 targeted tests, 3,322 regression passes, 8 skips, and 51 validation engine tests. The corresponding provider-only Cloudflare preflight run `43486369248` passed ordinary Chat Completions transport (HTTP 200), but its native function probe failed (HTTP 400, Cloudflare code 8007) and its ordinary labelled-text probe also returned HTTP 400. No repository evidence tool ran. The preflight was run against the same validated source commit.

Both failing probes construct **two consecutive `system` messages**, followed by a `user` message. The successful transport probe constructs one `system` message followed by one `user` message. The source also inserts a second leading system response-format instruction during AE-32C native and text fallback requests.

Qwen 3.8's upstream chat template has been documented to reject additional system messages, including a second leading system role, with the message `System message must be at the beginning`. Independently reported Cloudflare/Qwen adapter failures demonstrate the same pattern. This gives a specific, testable explanation of the observed failures, but **the redacted preflight errors do not prove that Cloudflare's error code 8007 means chat-template rejection**. That code remains unclassified unless a provider supplies direct confirmation.

References (retrieved 2026-11-13):
- https://github.com/QwenLM/Qwen3.8/issues/244
- https://github.com/anomalyco/opencode/issues/46481
- https://huggingface.co/Qwen/Qwen3.8-Flash-Next/discussions/75
- https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- https://developers.cloudflare.com/workers-ai/platform/errors/

## Correction

A pure transport-neutral helper, `providers/message_compatibility.py`, coalesces *only the contiguous leading run* of simple text system messages. The Cloudflare adapter opts into this behavior for exactly `@cf/qwen/qwen3.8-27b`, on both `/ai/v1/chat/completions` and `/ai/run/{model}` request paths. Original system contents retain order, with a blank-line separator, and caller input is not mutated. Neither the investigator nor evidence engine changes.

A non-leading system role is **never moved to the front**, because doing so could raise the trust authority of later or untrusted conversation content. It is rejected locally with a deterministic category. Multi-system messages containing unsupported metadata or non-text content are also rejected without an HTTP call rather than being silently reinterpreted.

The Cloudflare adapter reports only the number of coalesced envelopes and an allowlisted message compatibility category. A safely categorized upstream error explicitly mentioning the template restriction is reported as `message_role_sequence_rejected`; a generic code 8007 still has no guessed meaning. The provider-only preflight exposes these counts and categories even if its text probe fails, without logging source prompts or raw response bodies.

## What this does not change

- No requirement for JSON Schema, JSON-object mode, or native function calling.
- No provider secrets, original prompts, diagnosis content, or raw upstream error text in reports.
- No new repository tools, write tools, or autonomous repository modifications.
- No bypass of action-schema, evidence ID, source snapshot, budget, or exact-commit validation.
- No changes to OpenRouter, NaraRouter, workflow triggers, or the `main` branch.
- No unsupported claim that Qwen's live function calling is now operational.

## Tests and acceptance

The targeted G9.42 profile includes `tests/test_cloudflare_native_tool_calls.py`. Added adversarial fixtures cover both native and text request normalization, exact preservation of user and system content, a rejected mid-conversation system message, metadata-bearing system messages that cannot be merged safely, non-Qwen unchanged behavior, safe error categorization, and an entire offline preflight replay where native returns HTTP 400 but text succeeds. The replay executes no repository evidence tools.

Before any live provider call: manually upload the affected files as one commit; verify exact current branch content/hashes and pass the complete manual G9.42 profile. Then run the existing **provider-only Cloudflare Qwen preflight** using the new validation run ID. A safe successful outcome may have `native_tool_call_probe=provider_failed` but must have `text_response_probe=passed`, `response_mode_status=text_fallback_only` and `system_messages_coalesced=1`. If transport still fails, retain artifacts and investigate another request-property difference rather than weakening local validation.

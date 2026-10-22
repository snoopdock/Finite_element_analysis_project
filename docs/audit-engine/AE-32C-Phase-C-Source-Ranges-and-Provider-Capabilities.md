# AE-32C Phase C — Bounded Source Ranges and Provider Capability Contracts

## Purpose

Phase C hardens two shared contracts used by the read-only interactive investigator:

1. `read_source_file` must safely clamp an end-line request that extends beyond EOF while retaining an auditable requested range and actual range.
2. Provider-specific response features must be declared by the adapter, not inferred from a provider brand or from an OpenAI-compatible endpoint.

This change does not apply patches, execute repository code, or enable automatic commits or pushes.

## Source-read contract

For a non-empty indexed file:

- `start_line` must be an integer identifying an existing line.
- `end_line` must be an integer greater than or equal to `start_line`.
- An `end_line` beyond EOF is clamped to the file's final line.
- Responses retain `requested_start_line`, `requested_end_line`, `start_line`, `end_line`, and `total_lines`.
- `truncated` is true when the requested range extends beyond EOF or the output is shortened by the existing line/character bounds.
- Source hashes, path filtering, and secret redaction remain in force.

For an empty file, the only valid starting line is 1 and the actual end line is 0. A positive end request is retained as requested metadata and the actual range remains empty. Invalid types and invalid range order fail closed.

## Provider capability contract

`providers.capabilities.get_provider_capabilities` returns a normalized record for an adapter/model pair. Unknown features default to false. The record explicitly states that capability declarations describe adapter support and do not verify model behavior.

The initial capability keys are:

- `json_object_mode`
- `json_schema_mode`
- `native_tool_calls`
- `finish_reason_reporting`

Cloudflare explicitly declares JSON-object mode because its adapter exposes `chat_structured` with API-level `response_format: json_object`. It does not declare JSON Schema enforcement, native tool calling, or finish-reason reporting. Other adapters remain conservative unless they explicitly declare support.

AE-32C requests structured JSON mode only when both the adapter declaration and callable method are present. Regardless of mode, diagnosis JSON, allowed actions, evidence identifiers, source references, hashes, and claim-level citations continue to be validated locally. JSON-object mode is not treated as schema validation or as proof that the model response is correct.

## Validation

The G9.42 profile adds `tests/test_provider_capabilities.py`. The focused tests cover EOF clamping, invalid ranges, empty-file behavior, conservative capability defaults, and explicit adapter declarations. Run the G9.42 profile through the repository's manual validation dispatcher; do not enable push-triggered validation or live provider calls as part of this patch.

## Scope limits

This patch does not claim that a provider/model follows its declared format, does not add JSON Schema or native tool-call support, and does not change investigation budgets or finalization behavior. Live-provider evaluation remains a separate explicitly opt-in activity.

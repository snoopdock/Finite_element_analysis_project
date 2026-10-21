# AE-32C Corrective v15 — Unsupported-Action Recovery and Cloudflare Transport Retry

## Evidence reviewed

The v14 manual-validation run `39621228986` passed G9.42. The subsequent live runs used source commit `2c4a80eede27f17814d7e9c03bc18ffe8a3477f2` and main workflow commit `039eee3384f6ae02a7c94f3746c6084a3669b5ce`.

- OpenRouter run `39624259532` passed: 8 evidence-tool calls, 9 model rounds, 7 source references, and `references_resolved`. It recovered from one invalid final-action envelope. Keep this path unchanged.
- NaraRouter run `39623544238` stopped after round 1 with `unsupported_model_action`. Its report records only `reason=unsupported_action`, not the rejected action name or top-level keys. Therefore the precise malformed action cannot be reconstructed from the artifact; the patch adds safe diagnostics and bounded protocol recovery rather than guessing the response.
- Cloudflare run `39622892860` stopped at round 8 with `HTTPSConnectionPool(...): Read timed out. (read timeout=45)`, after 7 evidence records and one malformed-JSON recovery. The request error is a transport timeout, not a citation-validation failure. The configured investigator had reduced the Cloudflare adapter to one HTTP attempt, overriding its intended two-attempt allowance.

## Changes

### Unsupported model action recovery
- Replaces immediate termination for an unsupported `action` value with bounded recovery using the existing `max_invalid_tool_retries` limit.
- Records only the safe action label and top-level key names; it does not persist or echo arbitrary rejected values.
- Supplies the exact allowed envelopes: `tool_call` with `action`, `tool`, `arguments`, `reason`; or `final` with `action`, `diagnosis`.
- During finalization, feedback permits only the `final` action and never encourages another tool call.
- Adds a separate `unsupported_action_retries_used` counter and a clear exhaustion event.

### Cloudflare transport resilience
- Allows Cloudflare one additional HTTP attempt across the investigation, mirroring the existing NaraRouter retry-budget design.
- Uses adapter `http_attempts` telemetry to mark the retry as consumed only when more than one HTTP attempt occurred.
- Once consumed, later Cloudflare logical calls are restricted to one attempt. The successful OpenRouter path and its one-attempt behavior are unchanged.
- The retry is internal to the provider adapter and does not dispatch tools or bypass JSON, action, evidence, or citation validation.

### Regression coverage
- Tests recovery from an unsupported action without echoing arbitrary rejected values.
- Tests that finalization-phase recovery only allows a final diagnosis.
- Tests exhaustion of the unsupported-action recovery budget.
- Tests Cloudflare's single investigation-wide transport retry and return to single-attempt calls.

## Safety and unchanged behavior

- Strict JSON parsing, exact action schemas, source provenance, snapshot verification, and citation validation remain strict.
- No automatic action coercion or direct-tool-name mapping is introduced.
- The 10-model-round limit, 180,000-token budget, and provider-specific elapsed limits remain unchanged.
- OpenRouter provider configuration is unchanged.
- Cloudflare's 45-second request timeout and NaraRouter's 90-second request timeout remain unchanged; this patch adds a bounded retry rather than increasing the timeout.

## Installation

1. Install `STAGE1_SECTION_UUIDS/` on `stage1/section-uuids`, preserving relative paths and overwriting the listed files.
2. Install `MAIN_BRANCH/` on `main`, preserving relative paths.
3. Run G9.42 Manual Validation Dispatcher.
4. If it passes, rerun NaraRouter and Cloudflare individually; keep OpenRouter as the control.

## Validation status

No repository runtime, compilation, pytest suite, or live provider request was executed while preparing v15. ZIP and payload checksums verify packaging only. GitHub validation remains pending.

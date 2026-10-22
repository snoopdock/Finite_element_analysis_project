# AE-32C Phase E.1 — Finalization Reliability and Bounded Context

## Purpose

This patch addresses recurring failures observed in bounded live investigations: cumulative prompt growth during finalization, inconsistent enforcement of the phase-scoped malformed-JSON retry limit, and mixed finalization errors that were not governed by a shared recovery allowance.

It does not claim that a provider/model is diagnostically accurate. It improves protocol completion behavior while preserving strict evidence and source-reference validation.

## Changes

### 1. Rebuild finalization context from the evidence ledger

At every reserved finalization round, the investigator replaces the long evidence-gathering conversation with a bounded finalization context containing:

- A dedicated finalization-only system instruction; tool use is explicitly disabled.
- The original problem statement and a compact initial repository summary.
- Every ledger evidence ID, tool, status, response hash, and a bounded representation of the observed result.
- Exact source-reference candidates derived from the evidence ledger and checked against the expected source hashes.
- Only the latest finalization recovery feedback, if any; rejected raw model output and obsolete conversational turns are omitted.

The context is compacted against the remaining cumulative prompt-character budget divided across the remaining model rounds. If even the minimum representation cannot fit, the normal prompt budget still fails closed; the investigator does not silently exceed it. The report records context sizes, target, and whether the target was exceeded.

### 2. Enforce the configured JSON retry limit in finalization

The finalization phase now applies `max_finalization_invalid_json_retries` instead of exempting finalization from the limit. The counter measures recovery turns actually offered; the terminal malformed response is recorded separately through the recovery-exhausted event.

### 3. Share a finalization recovery budget

`max_finalization_recovery_retries` sets the number of additional finalization responses allowed after the first rejected response. The same counter governs malformed JSON, invalid envelopes, invalid diagnosis schemas/references, unsupported actions, and prohibited tool requests. Per-error counters remain available, but no individual path can bypass the common recovery budget. Evidence-gathering retry counters do not consume this finalization allowance.

Terminal outcomes remain fail-closed and report `finalization_recovery_budget_exhausted`, `invalid_model_json`, `invalid_final_action`, or another specific stop reason as appropriate.

### 4. Classify OpenAI-compatible adapter errors

The OpenAI-compatible adapter now records a bounded `last_error_code` and aggregate `error_counts` for transport failures, transient HTTP exhaustion, malformed completion envelopes, empty content, invalid JSON, response-size violations, and other adapter failures. This is telemetry only; it does not blindly retry HTTP 200 responses that lack `choices`.

The investigation report carries these non-secret error codes forward when available.

## Validation

G9.42 includes new regression cases for:

- Enforcing the configured finalization JSON retry limit.
- A mixed malformed-JSON / invalid-envelope sequence sharing one recovery budget.
- Compacting finalization context while retaining exact evidence IDs, source hashes, and source-reference candidates.
- Removing rejected raw model output from the compacted context while preserving the latest validation feedback.
- Explicit adapter classification for HTTP 200 responses with a malformed completion envelope.

## Safety and limitations

- No target-repository code is executed.
- No source-reference, evidence-ID, or source-hash validation is weakened.
- No live provider calls occur in the G9.42 profile.
- Context compaction may omit detail from evidence responses; the ledger hashes and exact source-reference candidates remain available, and the model must explicitly state when the retained detail is insufficient.
- A successful smoke gate remains protocol-completion evidence, not independent proof that a root-cause interpretation is correct.

# AE-32C Corrective v13 — Citation Recovery and NaraRouter Transport Resilience

## Evidence reviewed

Runs `39609688827` (Cloudflare), `39610038223` (NaraRouter), and `39611736824` (OpenRouter) used the same source and workflow revisions. G9.42 manual validation and all three preflights passed.

- OpenRouter completed with `diagnosis_submitted`, nine source references and resolved citations. This patch leaves its successful path unchanged.
- Cloudflare reached finalization but two diagnosis attempts were rejected: first with `source_reference_line_invalid`, then `source_reference_shape_invalid`. The report shows `max_invalid_final_attempts=1`, so no third correction was permitted. Raw invalid model output was not retained.
- NaraRouter used all ten model rounds and failed on round 10 with `nararouter response stream error: ChunkedEncodingError`. Earlier it recovered from malformed JSON and an invalid action envelope missing `reason`. The report shows the 180,000-token and 900-second budgets were not exhausted.

## Changes

### Cloudflare / citation correction
- Adds `_available_source_reference_candidates`, which derives exact path/line/hash tuples from successful evidence-ledger responses and filters candidates against the source manifest when available.
- Diagnosis-validation feedback now includes reason codes, exact required source-reference keys, positive-integer line rules, evidence binding requirements, and ledger-observed candidates.
- The live configuration allows two bounded invalid-final attempts, enabling a third final submission after two rejected diagnoses. Validation remains strict: candidates are suggestions grounded in evidence, not automatic repairs or accepted citations.

### NaraRouter / transport retry
- The investigator permits a maximum of one extra HTTP attempt across the entire NaraRouter investigation, and only until provider telemetry (`http_attempts`) shows that a retry was actually used.
- The first eligible NaraRouter provider call receives `max_retries=2`; subsequent calls revert to one attempt after a retry is observed. OpenRouter and Cloudflare retain one attempt per logical call.
- The report exposes the retry budget and records `nararouter_transport_retry_budget_consumed` with attempt counts only; it never records raw model output or upstream error bodies.
- This change does not execute a tool or accept a diagnosis automatically. A retried response must still pass strict JSON, action, evidence, and citation validation.

## Unchanged
- Ten model rounds, 180,000-token budget, provider-specific elapsed limits, strict JSON parsing, tool schema validation, source snapshot verification, citation provenance, and smoke-gate requirements.
- Successful OpenRouter path.
- Cloudflare structured JSON request path.
- No change to provider adapter source files; the existing adapter's bounded `max_retries` and `http_attempts` telemetry are used so the patch does not overwrite provider code not included in the latest run artifact.

## Installation

Install `STAGE1_SECTION_UUIDS/` on `stage1/section-uuids` and `MAIN_BRANCH/` on `main`, preserving relative paths. Run G9.42 Manual Validation Dispatcher first. If it passes, rerun Cloudflare and NaraRouter individually; keep OpenRouter as the control.

## Validation status

No repository runtime, compilation, pytest suite, or live provider request was executed while preparing this patch. Archive hashes verify packaging only; GitHub validation remains pending.

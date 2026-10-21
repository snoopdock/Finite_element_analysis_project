# AE-32C Corrective v17 — Phase-Scoped Strict-JSON Recovery

## Evidence reviewed

- G9.42 manual-validation run `39639565681` passed: 154 targeted tests, 3,112 regression tests, 8 skipped.
- Cloudflare live run `39642091076` failed with `stop_reason=invalid_model_json`. The report shows malformed strict JSON on rounds 5 and 7 during evidence gathering, consuming the two configured JSON-recovery retries. Round 8 had another malformed response after entering finalization; the investigator immediately stopped with `invalid_json_recovery_exhausted`, leaving no accepted diagnosis.
- NaraRouter live run `39642913735` passed on round 9 with `diagnosis_submitted`, 4 source references, and `references_resolved`. It recovered from an initial malformed response and a rejected final-action envelope.
- Cloudflare live run `39644408856` passed on round 8 with `diagnosis_submitted`, 10 source references, and `references_resolved`. It used the same source commit as the earlier failed Cloudflare run, indicating intermittent response-format behavior rather than a deterministic integration failure.

## Root cause

The investigator used a single global `max_invalid_json_retries` counter for both evidence gathering and finalization. When two malformed responses occurred during evidence gathering, the finalization round had no remaining repair opportunity. The reserved finalization rounds were present, but the shared JSON-recovery counter prevented the model from using them to correct a malformed final response.

## Correction

- Preserve `max_invalid_json_retries` as the evidence-gathering phase limit (default 2).
- Add `max_finalization_invalid_json_retries` as an independent phase limit (default 1).
- Track total, evidence-gathering, and finalization JSON-recovery counts separately.
- Include phase, phase-specific attempt count, remaining attempts, and total attempts in safe recovery telemetry.
- Keep malformed response contents out of messages, reports, and diagnostics.
- Configure live evaluations explicitly for two evidence-gathering retries and one finalization retry.
- Add a deterministic regression test that reproduces two malformed evidence-phase responses followed by a malformed finalization response and then a valid final diagnosis.
- Preserve the v16 fix that locates unsupported-action feedback by schema version and the earlier source-reference line test correction.

## Unchanged limits and safety

- Ten model rounds, three reserved finalization rounds, 180,000 total tokens, 200,000 prompt characters, and provider-specific elapsed deadlines remain unchanged.
- Strict JSON parsing, action schema validation, evidence provenance, snapshot verification, and citation validation remain mandatory.
- No malformed response is executed, echoed, or automatically repaired into an accepted action.
- No provider adapter, API endpoint, secret, model selection, or GitHub workflow is changed.

## Installation

Install `STAGE1_SECTION_UUIDS/` into the root of `stage1/section-uuids`, preserving relative paths and overwriting the listed files. Run G9.42 Manual Validation Dispatcher. If it passes, rerun Cloudflare first, then NaraRouter; keep OpenRouter as the control.

## Validation status

No repository runtime, compilation, pytest suite, or live-provider call was executed while preparing v17. Archive and payload checksums verify packaging only. GitHub validation remains pending.

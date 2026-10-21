# AE-32C Phase B — Finalization State-Machine Correction

## Phase A acceptance evidence

G9.42 run `39657285225` passed for source commit `438783548625d6b81d447e640af34290a4c61cb1`: 43 validation-engine tests passed, 155 targeted tests passed, and 3,113 regression tests passed with 8 skipped. The report and catalog receipt bind the result to that exact source commit.

## Problem

Malformed JSON, unsupported actions, invalid final-action envelopes, and invalid diagnosis structures had separate early-stop counters. During reserved finalization rounds, an individual counter could terminate the run before the configured finalization sequence was consumed.

## Change

- Add `finalization_rejections_used` telemetry for malformed JSON, unsupported actions, invalid final envelopes, and invalid diagnoses during finalization.
- Report actual finalization rounds used and reserved.
- Keep evidence-gathering retry caps unchanged.
- During finalization, prevent evidence-phase and per-error retry counters from prematurely terminating reserved finalization rounds.
- Keep `max_rounds`, elapsed-time, token, prompt-character, tool-call, snapshot, schema, provenance, and citation constraints enforced.
- Add a mixed-failure regression test: malformed JSON, invalid final envelope, then valid diagnosis across three reserved finalization rounds.
- Preserve the validated Phase A test fixture and diagnostics.

The reserved rounds remain the hard limit. No extra rounds are created, and a rejected final response is never accepted.

## Installation

Install `STAGE1_SECTION_UUIDS/` into `stage1/section-uuids`, preserving relative paths. Run G9.42 Manual Validation Dispatcher. Do not run live evaluations unless G9.42 passes.

## Validation status

No repository runtime, compilation, pytest suite, or live-provider call was executed while preparing Phase B. Checksums verify package integrity only.

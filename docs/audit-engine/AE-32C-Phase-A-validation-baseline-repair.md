# AE-32C Phase A — Validation Baseline Repair

## Evidence reviewed

G9.42 run `39647391501` rejected source commit `01514b25369aeb93f0f185b4d91341ca27b790e6`. The validation engine's 43 unit tests passed. The targeted suite reported 154 passes and one failure; the full regression suite reported 3,112 passes, one failure, and eight skips. Both failures refer to the same test:

`test_finalization_json_recovery_remains_available_after_evidence_budget_is_used`

The failing assertion was `assert report["diagnosis"] is not None`.

## Root cause from static inspection

The regression test was intended to isolate phase-scoped JSON recovery across nine model rounds. However, its `InvestigationLimits` overrode `max_rounds`, JSON retry limits, and finalization rounds while inheriting unrelated defaults of `max_total_prompt_chars=90_000` and `max_total_tokens=24_000`.

The investigator accumulates prompt-character reservations across calls while each provider call includes the growing conversation history. Repeated tool calls and recovery feedback therefore make prompt-size or estimated-token exhaustion a plausible earlier stop condition. The original assertion did not print `stop_reason`, budget telemetry, errors, or model-action trace, so the GitHub failure artifact did not establish the exact terminal condition.

Phase A corrects the test's scope by assigning test-local `max_total_prompt_chars=500_000` and `max_total_tokens=180_000`, within the class's supported validation ranges, so the intended nine-round protocol scenario is not blocked by unrelated default budgets. The assertion now prints the terminal state, budget, error events, and action trace if the diagnosis is still absent.

This is a test-fixture correction based on static inspection; it is not a claim that the original GitHub run recorded `prompt_size_budget_exhausted`. The exact stop reason will be visible if the corrected test still fails.

## Scope and invariants

- Only the regression-test file is modified; this patch does not change production code.
- Production prompt, token, elapsed-time, tool-call, and retry limits remain unchanged.
- Strict JSON parsing, final-action schema validation, evidence provenance, source-reference matching, snapshot verification, and citation validation remain unchanged.
- The earlier v16 feedback-selection fix and v14 source-reference line-value fix are retained.

## Installation

Install `STAGE1_SECTION_UUIDS/` into the root of `stage1/section-uuids`, preserving relative paths and overwriting the listed test file. Run G9.42 Manual Validation Dispatcher.

Acceptance requires the targeted suite and full regression suite to pass. If the test still fails, use the expanded assertion output to identify the exact stop reason before making any production changes.

## Validation status

No repository runtime, compilation, pytest suite, or live provider call was executed while preparing Phase A. ZIP and payload checksums verify packaging only. GitHub validation remains pending.

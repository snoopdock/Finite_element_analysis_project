# AE-32C Corrective v6 — Finalization-Aware Round Budget

## Problem established by live evaluation

The latest live run used eight model rounds and nine evidence calls including the initial repository summary, while consuming 29,741 provider-reported tokens against the 180,000-token cap. The source snapshot was verified and there were no schema or JSON parsing errors. The investigation ended with `model_round_budget_exhausted` because every model turn requested more evidence and no final diagnosis was submitted.

## Changes

- Adds `InvestigationLimits.finalization_rounds_reserved`, defaulting to one for compatibility with deterministic callers and configurable from one to four.
- The live evaluator reserves two of its eight model rounds for finalization.
- At the beginning of each reserved round, the investigator sends an explicit `finalization_mode` instruction to submit a diagnosis using collected evidence, or an explicitly inconclusive assessment if evidence is insufficient.
- Tool requests in finalization rounds are rejected before dispatch. The model receives structured feedback to finalize; the final reserved round remains available for a corrected final response.
- If the model continues to request tools in the last reserved round, the investigator stops with `finalization_budget_exhausted` rather than dispatching the tool or silently claiming success.
- The report records the reservation, start round, finalization rounds used, and rejected finalization-phase tool requests.
- The system prompt discourages redundant reads of the same path and line range.
- Deterministic regression tests cover successful finalization after a rejected tool request and safe termination when the model continues requesting tools.
- The live-limit test asserts that two finalization rounds are reserved.

## Safety contract

No unsupported diagnosis is manufactured. The model must still return the strict final JSON schema, cite actual evidence IDs, and pass source-reference validation. Finalization feedback is protocol guidance, not evidence. Rejected tool requests do not execute and do not create evidence-ledger entries. Token, elapsed-time, prompt-size, response-size, evidence-size, snapshot and citation safeguards remain enabled.

## Expected live behavior

For the live configuration (`max_rounds=9`, `finalization_rounds_reserved=2`), rounds 1–7 are available for evidence gathering. Rounds 8–9 are reserved for diagnosis and bounded recovery. If the model requests another tool in round 7, the request is rejected without dispatch and round 8 is used to request a final diagnosis. Repeated tool requests in round 8 terminate as inconclusive.

## Validation status

No repository runtime, compilation, test suite or live-provider request was run while preparing this patch. Archive checksums establish package integrity only. Apply the patch to `stage1/section-uuids`, run the G9.42 manual validation profile, then rerun the live evaluation from `main`.

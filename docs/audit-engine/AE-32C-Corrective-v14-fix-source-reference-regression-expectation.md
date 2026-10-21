# AE-32C Corrective v14 — Fix Source-Reference Regression-Test Expectation

## G9.42 evidence

Manual-validation run `39619246173` failed one targeted test and one corresponding full-regression test:

`tests/semantic_audit/test_ae32c_investigator.py::test_invalid_source_references_receive_exact_ledger_candidates_and_recover_twice`

The suite reported 3,107 passed, 1 failed, and 8 skipped. The independent validation-engine unit tests passed (43 tests).

## Root cause

The v13 test set a source-reference line to `999` but expected `source_reference_line_invalid`. The validator correctly treats `999` as a syntactically valid positive integer and rejects it later as `source_reference_not_observed`, because that line was not returned by the accepted evidence.

These reason codes express different invariants:

- `source_reference_line_invalid`: the line value has an invalid type or range (for example, `0`, a string, or a boolean).
- `source_reference_not_observed`: the line is a valid positive integer, but the exact path/line/hash tuple was not observed in the accepted evidence ledger.

## Correction

Change both intentionally invalid line values in the test from `999` to `0`. This directly exercises `source_reference_line_invalid` while leaving the later assertions for exact ledger-observed candidates and recovery behavior intact.

No production code, provider adapter, workflow, profile, validation rule, or runtime budget is changed.

## Installation and validation

Install the `STAGE1_SECTION_UUIDS/` payload on `stage1/section-uuids`, preserving relative paths. Run G9.42 Manual Validation Dispatcher again. If it passes, proceed to the live runs planned for v13.

## Validation status

No repository runtime, compilation, or tests were run while preparing v14. ZIP and payload checksums verify packaging only.

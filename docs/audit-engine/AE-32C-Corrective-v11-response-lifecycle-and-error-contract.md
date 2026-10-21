# AE-32C Corrective v11 — Response Lifecycle and Error Contract

## Evidence from the v10 G9.42 run

The latest manual-validation run reported 3,102 passed, 2 failed and 8 skipped in the main regression targets. The two failures were:

1. `tests/test_provider_response_limits.py::test_cloudflare_provider_rejects_oversized_decoded_text` — the test expects the phrase `character limit`; v10 returned `max_response_chars limit`.
2. `tests/test_provider_response_limits.py::test_cloudflare_http_error_omits_upstream_body` — the response error text was correctly body-free, but the response object was not closed (`response.closed == False`).

The independent validation-engine suite passed. The nested `tests/test_example.py::test_example` output belongs to negative-test demonstrations inside engine tests and is not one of the two final regression failures.

## Changes

- Align the oversized-response error string with the established `character limit` contract while retaining actual length and configured limit.
- Close obtained HTTP responses in a `finally` block on all paths: HTTP errors, retries/continues, extraction errors, oversized responses, invalid JSON and successful returns.
- Treat close as best-effort cleanup so a secondary close exception cannot mask the primary result/error.
- Extend focused tests to assert response closure on error and success, while preserving the body-free HTTP error contract.

## Scope

Only `providers/cloudflare.py`, the focused provider safety test, and this document change. No `MAIN_BRANCH/` payload is included. Provider settings, timeouts, retry counts, investigator logic, JSON mode and smoke-gate requirements are unchanged.

## Installation and validation

Apply the `STAGE1_SECTION_UUIDS/` payload to the root of `stage1/section-uuids`, preserving paths. Run G9.42 Manual Validation Dispatcher. Do not resume live provider runs unless validation passes.

## Validation status

No repository runtime, compilation, pytest suite or live provider request was run while preparing this patch. Archive and payload checksums verify packaging only.

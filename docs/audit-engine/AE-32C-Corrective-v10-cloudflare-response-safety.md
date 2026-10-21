# AE-32C Corrective v10 — Cloudflare Response Safety and Limits

## Cause of G9.42 failure

Manual validation on development commit `cc23d0d9de4666e060a80055d06cc3e7887a3095` and validation-engine commit `9f4243795853735345e36847b01d7bed09adbb3f` failed three Cloudflare-provider regression tests (3,097 passed, 8 skipped):

1. `test_cloudflare_http_error_does_not_echo_upstream_body`: the provider returned a sanitized excerpt of the upstream body instead of the stable body-free error expected by the safety contract.
2. `test_cloudflare_provider_rejects_oversized_decoded_text`: `CloudflareProvider` did not accept the existing `max_response_chars` configuration.
3. `test_cloudflare_http_error_omits_upstream_body`: the provider accessed `resp.text`, but the fake response deliberately did not implement that attribute; the adapter raised `AttributeError` instead of returning a safe error.

The independent validation-engine unit suite passed 43 tests. Do not run provider live evaluations until the G9.42 regression passes.

## Changes

- HTTP status errors now return `HTTP <status>: upstream error body omitted` and never access or parse the upstream body.
- Adds `max_response_chars` to `CloudflareProvider` as an optional trailing constructor parameter, preserving existing positional call compatibility.
- Supports `FEA_MAX_LLM_RESPONSE_CHARS`; defaults to 200,000 characters and validates the configured limit within 1..2,000,000.
- Rejects decoded model text longer than the configured limit before it is marked as a successful provider call.
- Reports response limit, oversized response count, and rejected character totals in provider statistics.
- Adds focused tests for body-free HTTP errors, oversized response rejection, boundary acceptance, and preservation of API-level JSON mode.

## Scope

Only the development branch is changed. No `MAIN_BRANCH/` files are included. This patch does not change timeouts, retry counts, model selection, the strict JSON parser, the investigation loop, or smoke-gate criteria.

## Install and validate

Apply `STAGE1_SECTION_UUIDS/` to the root of `stage1/section-uuids`, preserving paths. Run G9.42 Manual Validation Dispatcher. Only if it passes should the three provider live evaluations be rerun.

## Validation status

No repository runtime, compilation, pytest suite, or live provider request was executed while preparing this patch. Package hashes verify the archive only.

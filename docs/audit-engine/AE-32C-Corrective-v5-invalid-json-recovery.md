# AE-32C Corrective v5 — Invalid JSON Recovery and Prompt Budget Fix

## Findings addressed

The live evaluation completed four model rounds and four evidence-tool calls, then stopped on `invalid_model_json` / `invalid_strict_json` because the fourth provider response was not a valid strict JSON object. The source snapshot was verified and the token budget was not exhausted. This patch adds a bounded JSON-format correction opportunity; it does not loosen strict parsing.

The latest G9.42 regression also reported:
- `test_failed_source_read_gives_exact_path_recovery_guidance`: message wording did not contain the exact expected phrase.
- `test_controlled_incident_drives_real_evidence_tools_over_multiple_rounds`: the fixture projected 91,459 prompt characters against its 90,000-character test limit, while its token reservation remained within the configured 32,000-token budget.

## Changes

### 1. Strict JSON recovery
- Adds `InvestigationLimits.max_invalid_json_retries`, default `2`, configurable from `0` through `3`.
- A malformed, duplicate-key, or non-standard-constant JSON response is rejected without dispatching any tool.
- The investigator supplies protocol-only feedback requiring exactly one JSON object and no fences, commentary, duplicate keys, or trailing text.
- The malformed provider response is not echoed into later model context or report events; a fixed placeholder preserves the message-turn structure.
- The retry consumes a normal model round and all existing token, prompt-size, elapsed-time, response-size and other budgets.
- Repeated invalid JSON or exhausted model rounds stop with `invalid_model_json`, with safe parse-error codes and retry counts recorded.

### 2. Source-path feedback wording
The source-path guidance now explicitly asks the model to discover an "exact repository-relative path" present in the index. The path must still come from actual evidence; no guessed path is accepted.

### 3. Controlled incident prompt allowance
The deterministic six-round fixture sets `max_total_prompt_chars=120_000`, a bounded allowance above the observed 91,459-character projection. The general default and hard cap remain unchanged. This avoids conflating the fixture's prompt-history size with its separate token budget.

## Regression tests added/updated

- Duplicate JSON keys remain rejected when JSON recovery is disabled.
- One malformed response can be corrected and followed by a real evidence-tool call and final diagnosis.
- The malformed response text is not echoed into the subsequent model context or published report.
- Repeated malformed responses terminate after the configured retry allowance.
- Existing exact source-path guidance assertion is satisfied.
- The controlled incident fixture retains a finite prompt-size limit and must still complete its scripted evidence sequence.

## Validation

No repository runtime, compilation step, test suite, or live-provider call was executed during patch preparation. Archive hashes verify packaging only. Install this patch on `stage1/section-uuids`, run the G9.42 manual validation, then rerun the separately triggered live evaluation.

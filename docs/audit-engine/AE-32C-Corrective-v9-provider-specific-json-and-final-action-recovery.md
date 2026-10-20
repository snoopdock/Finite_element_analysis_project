# AE-32C Corrective v9 — Provider-Specific Structured Output and Finalization Recovery

## Evidence from the latest live runs

The G9.42 manual validation passed (141 targeted tests, 3,103 regression tests with 8 skipped, and 43 independent validation-engine tests). All three provider preflights passed, but full live evaluations stopped differently:

- OpenRouter: `invalid_final_action` after eight model rounds and eight evidence-tool calls. The current investigator immediately terminates when a parsed final action has any top-level key set other than exactly `action` and `diagnosis`; that branch does not use the bounded final-action correction opportunity.
- Cloudflare: `invalid_model_json` after eight rounds and six evidence-tool calls. The preflight's JSON probe passed, but it only exercised a short response. The selected Cloudflare model supports API-level JSON mode, which the live investigator was not requesting.
- NaraRouter: `elapsed_time_budget_exhausted` after eight rounds and three evidence-tool calls. Its preflight's one transport response took 28.256 seconds, while the full investigation had a 300-second elapsed-time limit.

The source snapshot was verified and each baseline request completed. These failures are not a common repository-checkout failure.

## Changes

### OpenRouter: bounded final-action shape recovery
- Treat a parsed `final` action with extra/missing top-level keys as a correctable final-action schema rejection.
- Give one bounded correction opportunity when a model round remains.
- Provide only expected top-level keys and the safe list of received key names; do not echo invalid action values.
- Record `final_action_rejected`, `final_action_recovery_exhausted`, and invalid-final-attempt counters in the report.
- If the correction is invalid again or no rounds remain, stop safely with `invalid_final_action`.

### Cloudflare: API-level JSON mode for investigator calls
- Add `CloudflareProvider.chat_structured`, which sends `response_format: {type: json_object}`.
- Use this method for AE-32C graph-assisted action calls only; the free-text baseline remains unchanged.
- Update the Cloudflare preflight to use the same API-level JSON mode, rather than relying on a prompt-only format request.
- Continue strict local JSON parsing, action-schema validation, evidence validation and citation checks. JSON mode does not bypass any validation.
- Record whether structured JSON mode was requested and how many such provider calls were made.

Cloudflare's current Workers AI JSON Mode documentation lists `@cf/meta/llama-3.1-8b-instruct-fast` as a supported model: https://developers.cloudflare.com/workers-ai/features/json-mode/

### NaraRouter: provider-specific elapsed-time budget
- Keep the 90-second request timeout and existing bounded retry configuration.
- Raise only the investigator elapsed-time budget for NaraRouter from 300 to 900 seconds.
- Retain the 300-second limit for Cloudflare and OpenRouter.
- Raise the outer live-evaluation GitHub Actions job timeout from 12 to 22 minutes to accommodate setup, the bounded NaraRouter investigation and artifact publication.

## Safety contract

No model action is automatically accepted merely because it is valid JSON. Tool schemas, source paths, evidence IDs, source hashes, final citations and snapshot provenance remain strictly validated. Rejected final actions are not executed or treated as evidence. All time, token, round, tool-call, response-size and workflow time limits remain finite.

## Install

Install `STAGE1_SECTION_UUIDS/` on `stage1/section-uuids` and `MAIN_BRANCH/` on `main`, preserving paths. Run G9.42 manual validation first, then the Cloudflare and NaraRouter preflights, and only then rerun the three full live evaluations.

## Validation status

No repository runtime, compilation, test suite or live provider call was run while preparing this patch. Package checksums verify archive integrity only. All implementation behavior remains subject to GitHub validation.

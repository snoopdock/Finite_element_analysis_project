# AE-32C Corrective v8 — Provider Compatibility Preflight

## Why this patch exists

The same AE-32C source commit and workflow commit produced three different outcomes:

- OpenRouter completed the investigation with eight model rounds, eight evidence-tool calls, seven accepted source references and `diagnosis_submitted`.
- Cloudflare completed the baseline and six evidence-tool calls, but three model responses failed strict JSON parsing (`json_syntax_error`) and the bounded JSON recovery allowance was exhausted. The run used 31,244 provider-reported tokens, so token exhaustion was not the cause.
- NaraRouter timed out on the baseline request after about 30 seconds (`ReadTimeout`), with zero reported tokens and no graph-assisted investigation. The workflow overrode the adapter's longer default timeout with 30 seconds and disabled retries.

These findings support provider-specific compatibility and transport investigations; they do not prove a defect in either upstream provider.

## Changes

1. Adds `provider_preflight.py`, a manual, bounded provider-only probe that never invokes repository evidence tools or executes the incident fixture.
2. All providers receive a small connectivity prompt. A non-empty response establishes transport completion; sentinel exactness is recorded separately.
3. Cloudflare additionally receives a prompt-only strict JSON action-shape probe using the same top-level action keys expected by the investigator. The artifact reports syntax and schema validity without storing raw response text.
4. Adds a manual workflow on `main` named **AE-32C Provider Compatibility Preflight (Manual)**. It requires explicit consent, checks only the selected provider secret, checks out `stage1/section-uuids`, and uploads artifacts even on failure.
5. Adds optional model selection to both the preflight and full live evaluation workflows.
6. Validates optional model overrides against a bounded provider-model identifier character set before provider initialization or endpoint construction.
7. Replaces the shared 30-second/one-attempt override with provider-specific settings: NaraRouter 90 seconds/2 attempts, Cloudflare 45 seconds/2 attempts, OpenRouter 30 seconds/1 attempt.
8. Adds deterministic offline tests for a passing transport probe, Cloudflare strict JSON success/failure, duplicate-key rejection, and transport failure.

## Interpretation

- NaraRouter preflight success means a small response was received; it does not guarantee a full multi-round run will complete. Failure with `ReadTimeout` despite 90 seconds and two attempts points toward endpoint/model latency or availability and should be investigated before changing the audit engine.
- Cloudflare JSON preflight tests the current prompt/request path, not an API-level constrained-output parameter. A failure confirms output-format incompatibility under this probe. A pass is useful but not sufficient to guarantee long-context tool-action compliance.
- No invalid JSON response is accepted or dispatched. Raw model responses and credentials are omitted from artifacts.

## Installation and validation

Apply `STAGE1_SECTION_UUIDS/` to the root of `stage1/section-uuids` and `MAIN_BRANCH/` to `main`, preserving paths. Run G9.42 manual validation first. Then run the new provider preflight from `main` for NaraRouter and Cloudflare. Only after preflight results are reviewed should the full live evaluation be rerun. Use the same optional model override for the full run if a different model passes preflight.

No local repository runtime, test suite, or live provider request was executed while preparing this patch. Package hashes verify archive integrity only.

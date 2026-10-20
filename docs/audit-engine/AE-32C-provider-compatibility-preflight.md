# AE-32C Provider Compatibility Preflight — Operator Guide

## Purpose

Use this workflow to isolate provider connectivity and Cloudflare strict-JSON behavior before spending calls on the full AE-32C investigation. It does not invoke evidence tools or execute the incident fixture.

## Run

1. Install the matching provider-preflight module from `stage1/section-uuids` and merge the workflow to `main`.
2. Open **Actions → AE-32C Provider Compatibility Preflight (Manual)** and run it from `main`.
3. Select one provider, optionally specify a model override, and explicitly confirm live calls.
4. Download the uploaded `ae32c-provider-preflight-...` artifact, even if the run fails.
5. For NaraRouter, inspect `transport_probe`, elapsed time, effective timeout/retry settings, HTTP status counts and safe error category. A successful preflight only proves a small request returned.
6. For Cloudflare, inspect both `transport_probe` and `json_action_probe`. The JSON probe uses Cloudflare's API-level `response_format: {type: json_object}` and then locally validates one strict JSON object with the investigator's action envelope. JSON mode constrains syntax but does not guarantee the action schema for every complex response.
7. After a provider/model passes preflight, rerun **AE-32C Live Evaluation (Manual)** from `main`, selecting the same provider and model override.

## Effective transport settings

- NaraRouter: 90-second request timeout, two attempts.
- Cloudflare: 45-second request timeout, two attempts.
- OpenRouter: 30-second request timeout, one attempt (the known-good control).

The full live evaluation remains bounded by nine model rounds, token budget, tool-call budget, snapshot checks and citation validation. Its elapsed-time budget is 900 seconds for NaraRouter and 300 seconds for Cloudflare/OpenRouter. The 22-minute workflow job timeout is a separate outer limit.

## What the result does and does not mean

A transport pass does not prove full investigation compatibility. A Cloudflare JSON probe pass does not guarantee all long-context model responses will satisfy the action schema. A failure should be interpreted from the status fields and safe diagnostics, not by assuming the repository or provider API is defective. The full smoke gate remains strict.

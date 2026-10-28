# AE-32C Focused Diagnostics — operator runbook

## Prerequisites
- Operational source patch reviewed/merged on `stage1/section-uuids`.
- New successful G9.42 run ID for that exact source commit.
- This workflow and comparison helper uploaded to `main`.
- Required GitHub Actions secrets configured.
- Do not use the previous validation run `40502970945` for the new source patch.

## NaraRouter
1. Actions → AE-32C Focused Diagnostics (Manual) → Run workflow on `main`.
2. Enter the new G9.42 run ID and choose `nararouter_smoke`.
3. Check live-call confirmation and start.
4. Open artifact `ae32c-focused-diagnostics-<run-id>-1`; inspect `nararouter-smoke.json`.

One HTTP attempt goes to the fixed endpoint `https://router.bynara.id/v1/chat/completions` with default model `agnes-2.5-flash`. No endpoint selection is offered. The output contains safe status/error structure and does not print raw provider messages.

- `completion_received`: endpoint/request returned a parseable completion.
- `error_param=model` or invalid-model code: inspect the configured model identifier.
- Request-field `error_param`: inspect that field only.
- 401/403: check credentials/permissions; 429: check quota/rate limit.
- No structured error code: keep endpoint fixed and inspect provider-side request logs/docs; do not guess.

## Cloudflare
1. Dispatch the workflow again with the same new G9.42 run ID.
2. Choose `cloudflare_focused`, baseline run ID `40503324230`, and confirm live calls.
3. Start. The historical artifact is downloaded before any new Cloudflare call.
4. Read `cloudflare-comparison.md` in the uploaded artifact.

The new run is one bounded baseline-plus-graph investigation, not a full round-robin. It compares required source coverage, successful `read_source_file` calls, direct citations, finalization rejection reasons, and recovery exhaustion against the old four trials.

- Incomplete coverage → fix deterministic read/prefetch path.
- Complete coverage but unbound evidence IDs → fix ledger binding/provenance.
- Operational gates pass → human-review the diagnosis; do not infer correctness.

Artifacts are retained even if the diagnostic outcome fails.

# AE-32C v3 batch gate and NaraRouter JSON capability probe

## Part A — Round-robin acceptance gate correction

The latest batch summary is `ae32c/batch-evaluation/v3`. It exposes:
- `expected_trials`
- `observed_trials`
- `baseline_completed`
- `graph_protocol_completed`
- `graph_evidence_complete`
- `overall_accepted_trials`
- `passed`

It does **not** expose the old ambiguous top-level `evidence_complete` field. The previous main workflow referenced that nonexistent key. The corrected workflow calls `tools/verify_ae32c_batch_acceptance.py`, which checks the v3 schema, the dispatch-derived denominator (`rounds × 3 providers`), observed count, baseline completion, graph protocol completion, graph evidence completeness, overall accepted count, and the batch `passed` flag. It remains fail-closed. It does not turn a partial batch into a pass.

## Part B — One-request NaraRouter JSON-object probe

The new manual workflow is:
**Actions → AE-32C NaraRouter JSON Capability Probe (Manual)**

Inputs:
- `validation_run_id`: a successful G9.42 run for the exact current `stage1/section-uuids` commit
- `nararouter_model`: default `laguna-s-2.1`
- `confirm_live_provider_calls`: checked explicitly

The workflow first verifies exact-commit G9.42 evidence, then makes at most one request to the fixed endpoint:
`https://router.bynara.id/v1/chat/completions`

It sends `response_format: {"type":"json_object"}` through the existing provider adapter. The NaraRouter capability opt-in environment variable is set only for this diagnostic job. It does not change default behavior for normal investigations. The provider retry count and logical-call budget are both one.

The prompt requests a tiny JSON object with marker `AE32_SMOKE_OK`. The artifact records only safe diagnostics: selected model, request mode, whether the format was requested, adapter opt-in declaration, HTTP status, allowlisted error metadata, response-envelope category, whether the response parsed as a JSON object, marker match, logical calls, HTTP attempts, and structured JSON call count. It does not persist raw model output or free-form provider error text.

Interpretation:
- HTTP 400 with `error_param=response_format` or `request_parameter_rejected`: the endpoint rejected the JSON-mode parameter.
- HTTP 200 with a malformed envelope: the upstream response did not satisfy the adapter's Chat Completions contract.
- HTTP 200 with `response_is_json_object=false`: a completion arrived but was not valid JSON-object content.
- All required probe fields passing: one-request evidence that this model/endpoint accepted the request and returned valid JSON. It does not establish reliable multi-round investigator compliance.

Do not enable NaraRouter JSON mode in ordinary AE-32C investigations based only on a successful smoke test. Review the artifact first, then make a separate source change and validate it if you decide to enable the mode in production.

## Upload order

1. Upload the two `stage1-section-uuids/` files to `stage1/section-uuids` and commit.
2. Run G9.42 on the new development commit. Do not use the previous validation run ID after changing the smoke tool.
3. Upload the `main/` files to `main` and commit.
4. Run the round-robin workflow only when useful, with the new validation run ID. Its final gate now reads the v3 contract.
5. Run **AE-32C NaraRouter JSON Capability Probe (Manual)** with that same successful validation run ID, model `laguna-s-2.1`, and explicit confirmation.
6. Upload the probe artifact here for interpretation.

The two workflows remain manual-only. No push/schedule trigger or automatic live provider call is introduced.

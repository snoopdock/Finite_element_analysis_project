# AE-32C E.5 — Manual round-robin workflow continuation

The Phase E.5 development-branch implementation removes the previous dependency where a baseline model failure prevented the graph-assisted condition from running. The existing **manual** `ae32c-round-robin-evaluation.yml` workflow is retained, including exact G9.42 validation gate, explicit live-provider consent, no push/scheduled trigger, sequential Cloudflare → NaraRouter → OpenRouter order, and a pause between evaluations.

Use **one dispatch** for up to four complete rounds. The workflow records a runner exit for every trial and uploads the full batch even if a trial fails. E.5's development-side offline assessor reports *baseline completion*, *graph protocol completion*, *graph evidence completeness*, and *overall accepted trials* separately. The v2 schema uses `graph_evidence_complete` for graph-condition evidence and `overall_accepted_trials` for trials passing every required gate; the workflow rejects missing or unsupported schema versions. The final workflow gate continues to fail when required conditions fail; it does not replace a missing baseline response with a successful graph assessment.

## Acceptance sequence

1. Apply and push the E.5 reporting-contract correction on `stage1/section-uuids` and the matching manual-workflow schema-gate/documentation patch on `main`, manually.
2. Run the central `Manual Validation Dispatcher` for branch `stage1/section-uuids`, profile `G9.42`, regression mode `profile`.
3. Require successful exact-commit evidence for the corrected source and record the **new** validation run ID.
4. Dispatch `AE-32C Round-Robin Provider Evaluation (Manual)` once on `main` using that ID, an explicit confirmation checkbox, up to four rounds, and a supported 30-, 60-, or 120-second pause.
5. Retain the gate output, every trial comparison, the batch summary and the workflow logs. Assess operational completion separately from causal correctness.

There are no automatically scheduled provider calls and no automatic code changes. The provider's HTTP 200 envelope can still fail safely if it is not the documented OpenAI-compatible `choices` format.

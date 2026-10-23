# AE-32C Phase E.4 — Source-Line Support and Provider Protocol Diagnostics

The existing **AE-32C Round-Robin Provider Evaluation (Manual)** workflow is deliberately retained. A single manual dispatch on `main` performs 1–4 cycles of Cloudflare → NaraRouter → OpenRouter, with 30/60/120-second pauses and a validated exact source commit. No scheduled or push-triggered provider calls are introduced.

Phase E.4 changes the **development-branch runner and batch assessor**, not the workflow's security/ordering contract:

- Each controlled incident declares two **textual witnesses**: `provider.total_calls` in `pipeline/extractor.py` and `self.calls` in `providers/adapter.py`. An exact direct source-read citation must point at the line containing each token. Merely citing `class Adapter:` or the README does not satisfy this check.
- The model receives a short provider-specific finalization **prompt hint** while the JSON schema, source-hash binding, evidence-ledger validation, and fail-closed behavior remain identical. The hint does **not** assert provider-native schema enforcement.
- Each trial's `SHA256SUMS.txt` is verified before the comparison can count toward a passing batch. The GitHub job continues after an individual failure and publishes the entire evidence bundle.
- `batch-summary.json` and the Actions step summary include provider-specific trial counts, protocol completion, evidence completion, textual witness coverage, observed median duration, and failed stop-reason distributions.

## Correct interpretation

A textual witness confirms only that a cited, validated source line contains the declared literal. It **does not prove** Python's dynamic attribute resolution, the absence of every possible inherited attribute, runtime causation, or correct repair. The original historical fixture is an evaluation scenario, not an assertion about current production files. Human adjudication remains necessary.

## Manual sequence

1. Apply E.4 development files to `stage1/section-uuids` and the optional main documentation/test additions if desired. Do not replace the existing dispatcher or round-robin workflow.
2. Run the `G9.42` Manual Validation Dispatcher against the new development commit and verify all detached evidence.
3. Manually dispatch the existing round-robin workflow on `main` using the **new** successful validation run ID, explicit live-consent checkbox, selected rounds and pause.
4. Inspect both `batch-summary.json` and all 12 individual trial artifacts when running four rounds. A failed batch is not an artifact-publication failure.

The runner's required source policy is specific to the controlled incident; the reusable investigator exposes an optional caller-declared source-line anchor mapping. It does not infer root causes from token strings.

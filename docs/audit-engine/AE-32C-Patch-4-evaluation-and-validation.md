# AE-32C Patch 4 — Incident Evaluation and Validation Readiness

**Patch ID:** `AE-32C-P4`  
**Provisional validation profile:** `G9.42`  
**Target branch:** `stage1/section-uuids`  
**Install order:** Patch 1 → Patch 2 → Patch 3 → Patch 4

## Purpose

Patch 4 completes the first AE-32C implementation sequence by adding a controlled historical provider-interface incident, a deterministic end-to-end test that uses the real AE-32B evidence tools with a scripted provider, and an explicitly opt-in live comparison runner.

The controlled incident contains a consumer that reads `provider.total_calls` and an adapter exposing `calls`. The auditor is not given a prescribed correction. The deterministic provider script requests source, test, graph-path, and workflow evidence over multiple rounds; this tests orchestration and evidence binding, not live model quality.

The fixture is never executed. It is read as source evidence only.

## New implementation components

- `audit_engine/semantic_audit/ae32c/evaluation.py`
  - Summarizes observable investigation metrics.
  - Builds a paired comparison record.
  - Renders a human-review-oriented Markdown report.
  - Publishes JSON, Markdown and SHA-256 manifest artifacts to a new directory outside the checkout.
  - Explicitly avoids automatic diagnosis-accuracy scores or claims of graph benefit.
- `audit_engine/semantic_audit/ae32c/live_evaluation.py`
  - Runs a no-tool baseline using the original error and one bounded source excerpt.
  - Runs the graph-assisted investigator against the same controlled source snapshot if the baseline succeeds and the snapshot fingerprint remains stable.
  - Uses the existing provider factory and provider adapters.
  - Requires `--confirm-live-provider-calls` before making any provider request.
  - Limits the baseline to one call (2,000 output tokens) and graph-assisted investigation to at most eight model rounds, twelve evidence-tool calls including the initial summary, 8,000 output tokens per call, 180,000 estimated/reported total tokens, 200,000 cumulative prompt characters and 300 seconds. These are per-run caps; they are deliberately larger than deterministic-test budgets so the live model can read the tool catalog and investigate across multiple rounds.
  - Does not execute fixture code, run shell commands, modify source files, apply patches, commit or push.
- `tests/semantic_audit/test_ae32c_patch4_incident_evaluation.py`
  - Exercises the real AE-32B source graph and evidence dispatcher using a deterministic fake provider.
  - Checks multi-round source, related-test, graph-path and workflow evidence requests.
  - Checks source citation resolution and that evaluation metrics do not claim accuracy automatically.
  - Confirms live evaluation requires explicit opt-in before provider construction.

## Live comparison procedure

The live runner is intentionally not included in the ordinary `G9.42` target tests. Those tests must remain deterministic and require no credentials.

Run only when an operator deliberately wants to spend provider calls. From the repository root, configure the selected provider's existing GitHub secrets/environment variables, ensure the `RUNNER_TEMP`-equivalent directory exists outside the checkout, and run:

```bash
python -m audit_engine.semantic_audit.ae32c.live_evaluation \
  --confirm-live-provider-calls \
  --repo-root tests/semantic_audit/fixtures/ae32c_provider_interface_incident \
  --output-dir "$RUNNER_TEMP"
```

Provider selection reuses `FEA_LLM_PROVIDER` and `FEA_LLM_MODEL` and the existing secret names:

- Cloudflare: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`
- NaraRouter: `NARAROUTER_API_KEY`
- OpenRouter: `OPENROUTER_TOKEN`

Never place secret values in command-line arguments or upload environment dumps. The script does not print credentials. It produces a unique directory containing `comparison.json`, `comparison.md`, and `SHA256SUMS.txt`. The JSON records both conditions, provenance, the graph-assisted report and objective usage metrics. The Markdown explicitly requires human review.

The runner first makes one baseline provider request. If that request fails or its response exceeds the configured limit, the graph-assisted condition is skipped to avoid spending additional calls on a failed paired evaluation. If the source manifest or graph fingerprint changes between conditions, the comparison records the mismatch rather than treating the conditions as comparable.

## How to review results

The automated comparison records process measurements only. It does not claim that the graph-assisted result is more accurate because it made more tool calls or cited more files.

A human reviewer should:

1. Confirm the source manifest and fixture identity.
2. Verify every material citation against the evidence ledger and source files.
3. Compare both diagnoses with the independently reviewed incident outcome.
4. Record unsupported claims, missed evidence, misleading graph relationships, and whether the graph-assisted path materially improved evidence coverage or reduced uncertainty.
5. Distinguish model/API success, tool success, investigation completion, citation resolution and causal correctness.

## Validation profile

`validation/profiles/G9.42.yaml` includes the Patch 1–4 deterministic tests and the established graph, provider, and audit integration tests, followed by the full `tests/` regression.

The live comparison runner is not called by the profile. A live-provider test must be deliberately invoked by an operator in a separate manual execution path.

## Workflow integration limitation

This patch does not add or modify a GitHub Actions workflow. The current `main` branch snapshot and the actual Manual Validation Dispatcher source were not supplied for this implementation. Do not guess at or replace the central dispatcher. Once its source is available, the live runner can be wired into a separately gated manual workflow or dispatcher option, with the provider secrets exposed only to that job.

## Validation status

The live evaluation limits are tested deterministically as configuration values; no local repository runtime, test suite, compilation or live-provider request was executed during patch preparation. Tests are authored but unexecuted. Archive checksums establish package integrity only; GitHub validation and acceptance remain pending.

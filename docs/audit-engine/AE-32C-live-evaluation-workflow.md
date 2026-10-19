# AE-32C Live Evaluation Workflow — Operator Guide

## Purpose

This patch adds a separate, manually triggered GitHub Actions workflow for the AE-32C controlled live-provider evaluation. It does not modify the existing Manual Validation Dispatcher, the validation registry, or the FEA full-pipeline provider benchmark.

The workflow definition must be installed on `main`, because GitHub exposes `workflow_dispatch` workflows from the default branch. The workflow then checks out and executes the AE-32C implementation from the fixed `stage1/section-uuids` branch.

## What the workflow does

1. Requires the workflow itself to be run from `main`.
2. Requires the operator to select a provider and explicitly check `confirm_live_provider_calls`.
3. Checks out `stage1/section-uuids` without persistent Git credentials.
4. Verifies that the AE-32C live evaluator, evidence tools, controlled incident fixture, provider-safe-error module, and G9.42 profile exist.
5. Installs only the minimal runtime dependencies needed by this evaluator (`requests` and `PyYAML`), rather than installing arbitrary requirements from the target branch.
6. Makes one baseline request and then, if the baseline succeeds, up to four graph-assisted investigation requests. Provider timeout is set to 30 seconds and retry count to one. The investigator has its own bounded rounds, tool calls, response sizes, token estimates, and 90-second budget.
7. Uploads the comparison report and run logs even when the evaluator or smoke gate fails.
8. Marks the workflow failed unless the baseline completes, the graph-assisted path performs multiple rounds and at least one evidence-tool call, the source snapshot is verified, and the final citations are resolved.

## Install

Copy:

`MAIN_BRANCH/.github/workflows/ae32c-live-evaluation.yml`

to:

`.github/workflows/ae32c-live-evaluation.yml`

on the repository's `main` branch. This patch contains no `STAGE1_SECTION_UUIDS/` payload and does not modify existing workflow files.

After the new workflow is merged into `main`, open GitHub → **Actions** → **AE-32C Live Evaluation (Manual)** → **Run workflow**.

Choose one provider and check the confirmation box only when you intend to make live API calls. If confirmation is absent, the workflow stops before checking out or running the target source. If the selected provider's secret is missing, the workflow stops before calling the provider.

## Required GitHub repository secrets

Use the existing secret names:

- Cloudflare: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`
- NaraRouter: `NARAROUTER_API_KEY`
- OpenRouter: `OPENROUTER_TOKEN`

Only the selected provider's secret values are passed to the live-evaluation step. Values are not printed. Do not put secrets into workflow inputs or command-line arguments.

Because the live evaluator must execute code from `stage1/section-uuids`, run this workflow only after reviewing the selected branch's current source commit. The branch is fixed in the workflow to avoid arbitrary ref selection. A repository environment with required reviewers can provide an additional approval boundary if desired.

## Reading the result

The uploaded artifact is named:

`ae32c-live-evaluation-<run-id>-<attempt>`

It includes `run-context.json`, `live-evaluation.log`, the runner exit code, `smoke-gate.json`, and the generated comparison JSON/Markdown plus checksum manifest.

A green smoke gate means only that the baseline responded, the graph-assisted process made multiple model rounds and evidence calls, the snapshot was verified, and citations resolved. It does **not** establish causal correctness or prove that graph assistance improves accuracy. A human must compare the report with the independently reviewed incident outcome.

A failed gate still uploads evidence. Review the Actions summary and artifact before deciding whether a corrective patch is justified.

## Safety and scope

- Trigger: `workflow_dispatch` only; no push, pull-request, schedule, or automatic trigger.
- Repository permissions: `contents: read`.
- Target branch: fixed to `stage1/section-uuids`.
- Job timeout: 12 minutes.
- Provider timeout: 30 seconds; retries: one.
- Provider-call budget: one baseline request plus at most four graph-assisted rounds.
- No target fixture execution, shell tool, source modification, patch application, commit, or push.
- Output is written under `$RUNNER_TEMP`, outside the source checkout.
- Existing validation workflows remain unchanged.

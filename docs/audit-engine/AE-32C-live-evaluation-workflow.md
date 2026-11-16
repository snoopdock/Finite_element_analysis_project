# AE-32C Live Evaluation Workflow — Operator Guide

## Purpose

This guide documents the separate, manually triggered GitHub Actions workflow for the AE-32C controlled live-provider evaluation. Corrective v9 also adds a separate provider-compatibility preflight workflow. Neither workflow modifies the existing Manual Validation Dispatcher, the validation registry, or the FEA full-pipeline provider benchmark.

The workflow definitions must be installed on `main`, because GitHub exposes `workflow_dispatch` workflows from the default branch. Each workflow checks out the AE-32C implementation from the fixed `stage1/section-uuids` branch. The optional model override accepts a bounded model identifier containing letters, digits, `@`, `.`, `_`, `:`, `/`, or `-` only.

## What the workflow does

1. Requires the workflow itself to be run from `main`.
2. Requires the operator to select a provider and explicitly check `confirm_live_provider_calls`.
3. Checks out `stage1/section-uuids` without persistent Git credentials.
4. Verifies that the AE-32C live evaluator, evidence tools, controlled incident fixture, provider-safe-error module, and G9.42 profile exist.
5. Installs only the minimal runtime dependencies needed by this evaluator (`requests` and `PyYAML`), rather than installing arbitrary requirements from the target branch.
6. Uses provider-specific transport timeouts: NaraRouter 90 seconds, Cloudflare 45 seconds, and OpenRouter 30 seconds. Cloudflare and NaraRouter may each use one investigation-wide extra HTTP attempt when a transient transport failure occurs; after the extra attempt is consumed, later logical calls are limited to one HTTP attempt. OpenRouter remains at one HTTP attempt per logical call. The workflow makes one baseline request and then, if the baseline succeeds, up to ten graph-assisted model calls. The investigator retains its own bounded rounds, tool calls, response sizes, token estimates, and provider-specific deadline: 900 seconds for NaraRouter and 300 seconds for Cloudflare/OpenRouter.
7. Uploads the comparison report and run logs even when the evaluator or smoke gate fails.
8. For the controlled provider-interface fixture, requires a complete, non-truncated `trace_execution_context` call for `pipeline/extractor.py`, inspection of every surfaced candidate, and complete reads of `main.py` and `providers/factory.py`.
9. Reports direct required-source evidence coverage separately from broader investigation-context completeness. The smoke gate fails if either dimension is incomplete.
10. Marks the workflow failed unless the baseline completes, the graph-assisted path performs multiple rounds and evidence-tool calls, the source snapshot is verified, required source citations resolve, and the context-discovery contract passes.

## Install

Copy both workflow files to the matching paths on the repository's `main` branch:

- `MAIN_BRANCH/.github/workflows/ae32c-live-evaluation.yml` → `.github/workflows/ae32c-live-evaluation.yml`
- `MAIN_BRANCH/.github/workflows/ae32c-provider-compatibility-preflight.yml` → `.github/workflows/ae32c-provider-compatibility-preflight.yml`

Corrective v9 also adds the provider-preflight module and tests on the development branch. Install the `STAGE1_SECTION_UUIDS/` payload on `stage1/section-uuids` and the `MAIN_BRANCH/` payload on `main`, preserving paths.

After the workflows are merged into `main`, open GitHub → **Actions** → **AE-32C Live Evaluation (Manual)** → **Run workflow** for a full investigation, or **AE-32C Provider Compatibility Preflight (Manual)** for a provider-only check.

Choose one provider, optionally provide a model override, and check the confirmation box only when you intend to make live API calls. If confirmation is absent, the workflow stops before checking out or running the target source. If the selected provider's secret is missing, the workflow stops before calling the provider.

## Required GitHub repository secrets

Use the existing secret names:

- Cloudflare: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`
- NaraRouter: `NARAROUTER_API_KEY`
- OpenRouter: `OPENROUTER_TOKEN`

Only the selected provider's secret values are passed to the live-evaluation step. Values are not printed. Do not put secrets into workflow inputs or command-line arguments.

Because the live evaluator must execute code from `stage1/section-uuids`, run this workflow only after reviewing the selected branch's current source commit. The branch is fixed in the workflow to avoid arbitrary ref selection. A repository environment with required reviewers can provide an additional approval boundary if desired.

## Mandatory context-discovery contract (E.7-R.3N.7.1)

The controlled incident evaluation passes these explicit arguments to the Stage1 evaluator:

- `--require-complete-investigation-context`
- `--required-context-target pipeline/extractor.py`
- `--required-context-path main.py`
- `--required-context-path providers/factory.py`

The investigator rejects a final diagnosis while this contract is incomplete. It requires a successful, non-truncated static trace for the exact target, completion of `find_related_tests` and `discover_case_context`, and inspection of every surfaced candidate. For this fixture, the smoke gate additionally verifies that the trace classifies `main.py` as both a static caller and Python entrypoint, and `providers/factory.py` as entrypoint context; both must be surfaced and fully read before the diagnosis can be accepted.

The smoke gate uses schema `ae32c/live-smoke-gate/v3` and reports these separately:

- `required_source_evidence_complete`: direct required-source reads and root-cause citations;
- `investigation_context_discovery_complete`: all required discovery operations are complete and non-truncated;
- `execution_context_trace_invoked_for_required_target`: the exact target trace completed;
- `required_entrypoint_and_factory_context_read`: both benchmark-required context paths were surfaced and read.

These are static evidence-coverage requirements. They do not execute repository code, establish runtime behavior, or assess diagnostic accuracy. A failed context gate still uploads the comparison and logs for review.

## Reading the result

The uploaded artifact is named:

`ae32c-live-evaluation-<run-id>-<attempt>`

It includes `run-context.json`, `live-evaluation.log`, the runner exit code, `smoke-gate.json`, and the generated comparison JSON/Markdown plus checksum manifest.

A green smoke gate means only that the baseline responded, the graph-assisted process made multiple model rounds and evidence calls, the snapshot was verified, required source citations resolved, and the controlled context-discovery contract completed. It does **not** establish causal correctness or prove that graph assistance improves accuracy. A human must compare the report with the independently reviewed incident outcome.

A failed gate still uploads evidence. Review the Actions summary and artifact before deciding whether a corrective patch is justified.

## Safety and scope

- Trigger: `workflow_dispatch` only; no push, pull-request, schedule, or automatic trigger.
- Repository permissions: `contents: read`.
- Target branch: fixed to `stage1/section-uuids`.
- Job timeout: 22 minutes. NaraRouter may use up to 900 seconds inside the investigator; the outer job timeout includes setup and artifact publication.
- Provider-specific request settings: NaraRouter 90 seconds/2 attempts; Cloudflare 45 seconds/2 attempts; OpenRouter 30 seconds/1 attempt.
- Provider-call budget: one baseline request plus at most ten graph-assisted model calls.
- No target fixture execution, shell tool, source modification, patch application, commit, or push.
- Output is written under `$RUNNER_TEMP`, outside the source checkout.
- Existing validation workflows remain unchanged.


## Provider compatibility preflight (Corrective v9)

Before a full live investigation on Cloudflare or NaraRouter, run **Actions → AE-32C Provider Compatibility Preflight (Manual)** from `main`. It makes only a small provider probe and uploads a report even when the probe fails. For Cloudflare it performs a transport probe followed by a strict-JSON action-shape probe using API-level `response_format: {type: json_object}`. The default `@cf/meta/llama-3.1-8b-instruct-fast` model is listed in Cloudflare's current JSON Mode supported-model documentation. The probe validates both JSON syntax and the action envelope, but does not guarantee schema compliance for every long-context response. For NaraRouter it performs a transport-only probe.

The full live evaluation supports an optional model override so a model that passes preflight can be selected for the full run. Leave it blank to use the provider default. Request-level settings are NaraRouter 90s/2 attempts, Cloudflare 45s/2 attempts, and OpenRouter 30s/1 attempt. During investigation calls, the investigator limits each provider call to one HTTP attempt and applies the elapsed-time budget; this prevents hidden retries from overrunning the investigation deadline.

Cloudflare or NaraRouter may use one bounded transport retry across the entire investigation. The retry is recorded in the report, does not execute tools, and is separate from the ten-model-round limit.


## Exact-commit G9.42 prerequisite (Phase D)

Both this live-evaluation workflow and the provider-compatibility preflight now require the run ID of a successful, manual **Manual Validation Dispatcher** run. The gate checks that the run came from the central dispatcher on `main`, retrieves its exact evidence artifact, verifies G9.42 and the source commit, and runs the central detached-evidence and provenance-catalog verifiers.

The provider job checks out the exact commit that passed validation; it does not resolve `stage1/section-uuids` to a newer HEAD after the gate. Missing, expired, failed, stale, or mismatched validation evidence blocks the provider job before provider secrets are made available.

See `AE-32C-Phase-D-Exact-Commit-Validation-Gate.md` for the evidence bindings and operator procedure.


## E.7-R.3N.7.2 — retry-aware live smoke gate

The v3 smoke gate evaluates the exact-target trace from
`required_context_contract.target_trace_final_status` and
`target_trace_completed_call_count`. It does not require the aggregate trace
status to be `completed` independently of that target-specific contract.
Overall discovery completeness remains a separate gate and still requires all
three discovery operations to have a successful complete, non-truncated result.

The report retains failed-attempt counts and whether an operation recovered
after a retry. A recovered operation is not represented as if the failed
attempt never occurred.

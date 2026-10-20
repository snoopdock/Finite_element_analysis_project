# AE-32C Corrective v7 — Provider Call Budget Alignment

## Observed failures

The live evaluation at source commit `619fb3dd4b62d6bc72d1ce61476bdf61c4d5ccae` reached model round 9 and then recorded `provider_failure: Local logical-call budget exhausted`. The report shows `max_rounds=9` while the live evaluator constructed the graph-assisted provider with `max_calls=8`. The provider's local logical-call guard therefore rejected the ninth model request before it reached Cloudflare.

The G9.42 run `39434259835` had one regression failure in `test_finalization_rounds_reject_extra_tools_and_reach_final_diagnosis`. That test configured a growing full-context prompt but only a 12,000-token cumulative reservation. The investigator reserves estimated prompt tokens plus the maximum response on every call. The test budget is raised to 32,000 and its assertion now reports the stop reason and budget diagnostics if a different guard still prevents completion.

## Changes

- Defines `LIVE_GRAPH_MAX_ROUNDS = 9` and derives `LIVE_GRAPH_MAX_CALLS` from it.
- Uses the same constant in `InvestigationLimits.max_rounds`.
- Updates the explicit CLI consent text, workflow input description, and operator guide to say one baseline request plus up to nine graph-assisted model calls.
- Adds a regression assertion that the provider logical-call cap equals the investigator round cap.
- Raises only the affected deterministic test's cumulative token reservation from 12,000 to 32,000; production live budgets are unchanged.
- Adds failure diagnostics to the affected test.

## Safety

The patch does not disable provider call limits. It aligns the provider's maximum logical calls with the investigator's maximum model rounds. The investigator's existing token, prompt-size, elapsed-time, tool-call, response-size, snapshot and citation controls remain active. Invalid model actions are still rejected and final diagnoses must still pass reference validation.

## Installation

This patch has two branch-specific payload roots:

1. Install `STAGE1_SECTION_UUIDS/` into `stage1/section-uuids`.
2. Install `MAIN_BRANCH/` into `main`. These main-branch changes only update the workflow confirmation description and operator guide; they do not change workflow execution steps or the central validation dispatcher.

Run G9.42 manual validation first. If it passes, rerun AE-32C Live Evaluation (Manual) from `main` and explicitly confirm live provider calls.

## Validation status

No repository runtime, compile, test suite, or live provider call was executed while preparing this patch. Package and manifest checksums verify packaging only. GitHub validation remains pending.

# AE-32D benchmark starter

This directory is a **design scaffold**, not a completed benchmark or score report.

## Files

- `case.schema.json` — JSON Schema for a benchmark case.
- `manifest.schema.json` — JSON Schema for the benchmark manifest.
- `manifest.json` — versioned case inventory and benchmark status.
- `cases/AE32D-CANDIDATE-PROVIDER-INTERFACE-001.json` — the existing controlled interface incident as a machine-verified regression candidate.
- `cases/AE32D-CANDIDATE-BRANCH-UNBOUND-001.json` — synthetic control-flow defect candidate.
- `cases/AE32D-CANDIDATE-NO-DEFECT-001.json` — complete-initialization negative control.
- `cases/AE32D-CANDIDATE-AMBIGUOUS-PROVIDER-001.json` — incomplete provider evidence / abstention candidate.
- `cases/AE32D-CANDIDATE-EXCEPTION-SWALLOW-001.json` — exception-flow defect candidate.
- `cases/AE32D-CANDIDATE-DATAFLOW-STALE-VALUE-001.json` — stale intermediate value at output-sink defect candidate.
- `tools/ae32d_verify_extended_cases.py` — deterministic verifier for the two additional defect families.
- `tools/ae32d_verify_case_matrix.py` — deterministic verifier for the three pinned synthetic case families. Its report records source identity, file hashes, runtime observations, and explicit non-adjudication limits.

## Adding cases

1. Use an exact source commit and immutable fixture or checkout path.
2. Establish machine-checkable facts through immutable source identity, structural checks, tests, and runtime reproduction wherever possible.
3. Record supporting and counterevidence, acceptable alternative explanations, and whether abstention is correct.
4. Keep machine-verification evidence separate from benchmark gold labels; an LLM judge alone is not ground truth.
5. Keep pending or disputed cases out of the primary score.
6. Include positive, negative, no-defect, and ambiguous cases across multiple defect families.
7. Freeze the case set, rubric, prompts, model configuration, budgets, and scorer before scoring.

The pilot target is 6–10 adjudicated cases; expansion toward 30–50 cases follows only after the annotation and scoring process is shown to be reliable. The existing provider-interface incident is one regression case, not a sufficient benchmark by itself.

## Manual validation

Validate the candidate case against `case.schema.json` and the manifest against `manifest.schema.json` using a JSON Schema 2020-12 validator. Preserve the schema and manifest versions with every report. Do not add model outputs or benchmark scores until the case ground truth and scoring rubric have been reviewed and frozen.


## Current matrix validation

The three additional fixtures are pinned to `dd80be6e7a3e0a912beace92ce0fac446ea6ed61`. The AE-32D workflow successfully verified all three at run [46010190530](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46010190530). The inventory currently contains six candidate records, zero adjudicated records, and zero primary-score-eligible records. The numeric lower bound of the 6–10-case pilot target is reached; the adjudication, rubric approval, and freeze gates remain open. The exception/data-flow verifier passed at [run 46010847618](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46010847618).


## Machine-verification evidence ledger

`machine-verification-ledger.json` and its schema map each of the six cases to the immutable source revision, verifier revision, workflow run, and artifact. The validator rejects missing/duplicate/orphan case records, mismatched source commits, or any ledger attempt to grant primary eligibility or claim independent human adjudication. Ledger validation passed at [run 46011287913](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46011287913).

## AE-42 — exploratory machine-reference evaluation (not gold scoring)

- `machine-reference-registry.json` stores six fixture-contract-derived provisional outcomes. It is separate from each case's `ground_truth.label`.
- `machine-reference-registry.schema.json` constrains those records to machine-derived references, no independent adjudication, and no primary eligibility.
- `exploratory-trials.schema.json` defines A/B/C trial records. Each record is bound to the case's immutable source commit and a configuration digest. Failed, abstaining and missing outcomes remain explicit.
- `tools/ae32d_exploratory_evaluation.py` validates registry-to-manifest/case/ledger consistency and calculates exploratory-only metrics with raw denominators.
- `tests/semantic_audit/test_ae32d_exploratory_evaluation.py` tests source binding, duplicate rejection, missing-trial accounting, and the non-promotion boundary.

The scorer reports provisional defect detection, false-positive, abstention, ambiguous-case abstention, error and missing counts separately for A/B/C. Its output is always marked `exploratory_only_not_gold_adjudication`, sets `primary_benchmark_score=false`, and never writes case records. No A/B/C model/provider performance result is claimed until actual trial outputs are supplied and scored.

The machine-reference registry is not a substitute for independent adjudication. All six case labels remain `pending_adjudication`; all six cases remain excluded from primary scoring. Rubric approval, pilot freeze and gold adjudication remain open.

## AE-43 readiness gate

The next stage is an offline importer/normalizer for real A/B/C trial artifacts. No qualifying AE-32D A/B/C output bundle is currently tracked. Existing AE-32C provider batch records assess protocol/evidence completion and leave diagnostic accuracy unassessed; the separate FEA provider benchmark evaluates document-generation runs. Neither can be converted into AE-32D defect outcomes. See `docs/audit-engine/AE-43-Exploratory-Trial-Integration-Readiness.md`.


## AE-45 — deterministic A/B condition contracts

- `sanitized-task-projection.schema.json` is the allowlisted input contract for A/B. It contains the task statement, declared scope, constraints and exact source SHA, but no ground-truth, review, machine-reference or scorer fields.
- `condition-report.schema.json` defines the evidence-bound condition report, explicit decision, coverage, counterevidence, limitations and execution trace. Failed infrastructure states cannot be represented as `no_defect`.
- `tools/ae32d_trial_contracts.py` builds the sanitized projection by selecting approved fields and computing a canonical task-contract digest.
- `tests/semantic_audit/test_ae32d_ab_contract_schemas.py` tests strict schemas, hidden-field exclusion, digest/source shape, explicit decisions, evidence hash constraints and abstention.

These are contract-boundary components only. No A/B executor or trial output exists yet. The workflow runs the new tests; inspect the resulting Actions run before advancing to A1.

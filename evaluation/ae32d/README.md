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

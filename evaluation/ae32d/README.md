# AE-32D benchmark starter

This directory is a **design scaffold**, not a completed benchmark or score report.

## Files

- `case.schema.json` — JSON Schema for a benchmark case.
- `manifest.schema.json` — JSON Schema for the benchmark manifest.
- `manifest.json` — versioned case inventory and benchmark status.
- `cases/AE32D-CANDIDATE-PROVIDER-INTERFACE-001.json` — the existing controlled interface incident as a candidate only. It is machine-verified as a regression fixture at its pinned source commit. The evidence record is in the case JSON; it remains excluded from the primary score because machine reproduction is not the same as benchmark gold-label eligibility.

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

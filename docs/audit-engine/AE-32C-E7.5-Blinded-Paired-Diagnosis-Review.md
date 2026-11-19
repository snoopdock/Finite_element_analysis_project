# AE-32C E.7.5 — Blinded Paired-Diagnosis Review

## Status

Implementation increment for the E.7 independent-review exit criterion. This is an offline review tool; it does not call providers or create ground truth automatically.

## Why this increment follows E.7.4

The latest G9.42 validation (run `44462422110`) passed for Stage1 commit `677c3aa555228844322db1af80c33bb68b6809e`:

- 53 validation-engine tests passed.
- 456 G9.42 targeted tests passed.
- 3,446 full regression tests passed.
- 8 skipped; no failures.
- Detached evidence and provenance catalog verification passed.

The validation archive does not include a new live matched-pilot run. E.7.4 is therefore validated as code, but the next live pair must still demonstrate the isolation gate before it can enter blinded review.

## What is added

- `audit_engine/semantic_audit/ae32c/blind_pair_review.py`: pair isolation checks, anonymized packet generation, reviewer template generation, review validation, descriptive agreement, and post-review unblinding.
- `tools/ae32c_blind_pair_review.py`: CLI for prepare, validate, agreement, and unblind.
- `evaluation/ae32c/blind_pair_review.schema.json`: reviewer form schema.
- `evaluation/ae32c/blind_pair_review_rubric.md`: review procedure and scoring dimensions.
- `tests/semantic_audit/test_ae32c_blind_pair_review.py`: deterministic tests, including rejection of prior control leakage.
- G9.42 target list includes the new test module.

## Important experimental safeguard

The tool independently checks the actual control/treatment available-tool catalogs and recorded calls. It does not rely solely on `graph_tool_difference_isolated`. It rejects a control that still exposes or calls any of:

- `graph_neighbors`
- `graph_path`
- `trace_execution_context`
- `find_related_tests`
- `find_workflow_context`

The old pilot artifact `44452337966` is expected to fail this entry gate because its control tool catalog still included graph-derived relationship tools. That is a regression fixture, not a candidate for adjudication.

## CLI

Prepare packets from a completed matched pair:

```bash
python tools/ae32c_blind_pair_review.py prepare \
  --comparison run/comparison.json \
  --control-report run/control.report.json \
  --graph-report run/graph-enabled.report.json \
  --output-dir blind-review-output
```

Validate one reviewer submission:

```bash
python tools/ae32c_blind_pair_review.py validate \
  --packet blind-review-output/reviewer-1/packet.json \
  --review blind-review-output/reviewer-1/review.json
```

Compare two independently completed reviews:

```bash
python tools/ae32c_blind_pair_review.py agreement \
  --packet blind-review-output/reviewer-1/packet.json \
  --reviewer-a blind-review-output/reviewer-1/review.json \
  --reviewer-b blind-review-output/reviewer-2/review.json \
  --output blind-review-output/steward/agreement.json
```

Reveal the condition mapping only after both reviews are validated:

```bash
python tools/ae32c_blind_pair_review.py unblind \
  --key blind-review-output/steward/unblinding-key.json \
  --agreement blind-review-output/steward/agreement.json \
  --output blind-review-output/steward/unblinded-result.json
```

The `steward/` directory must never be sent to reviewers.

## Interpretation boundary

- Reviewers assess diagnoses and claim support, not provider protocol completion.
- Textual witnesses and resolved evidence IDs are not semantic proof.
- Agreement does not automatically establish truth.
- One pair is exploratory; do not claim general graph benefit or causal accuracy.
- Keep provider/model metadata and condition mapping sealed until both reviews are complete.
- No main-branch workflow or provider secret changes are required.

## Validation boundary

The package's new tests are deterministic and require no network or provider quota. A fresh G9.42 run on the exact commit after manual upload remains the acceptance gate.

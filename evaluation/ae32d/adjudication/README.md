# AE-32D adjudication templates

These templates support independent **ground-truth case review**, not automatic scoring.

## Order

1. Freeze the candidate case source and verify its source SHA and manifest.
2. Give Reviewer 1 and Reviewer 2 separate copies of `reviewer-1.template.json` and `reviewer-2.template.json`.
3. Reviewers independently inspect the source and permitted reproduction evidence without seeing each other's labels or provider/model outputs.
4. Preserve each completed JSON form and calculate its SHA-256.
5. Complete `adjudication-record.template.json`, recording agreement/disagreement, final label, evidence basis, and eligibility.
6. Keep the case out of the primary score unless adjudication and verification are complete.

## Template rules

- Replace every `REPLACE_...` value.
- Do not leave `pending_adjudication` or `not_assessed` in a submitted final form.
- Set the blindness attestation to `true` only if it is truthful.
- `review_completed_at` and `decided_at` must be ISO 8601 timestamps.
- A reviewer may conclude `ambiguous` or `pending_adjudication`; do not force a defect label.
- The adjudication template intentionally starts with `primary_benchmark_eligible: false`.
- Do not place model outputs into the ground-truth reviewer packet.
- Do not score E.5 output as AE-32D condition A: the E.5 baseline is a single-response model, not the deterministic audit baseline.

## Files

- `reviewer-form.schema.json` — schema for independent reviewer forms.
- `reviewer-1.template.json`, `reviewer-2.template.json` — independent copies.
- `adjudication-record.schema.json` — schema for the adjudication record.
- `adjudication-record.template.json` — intentionally pending record.
- The rubric and pilot plan live in `evaluation/ae32d/`.

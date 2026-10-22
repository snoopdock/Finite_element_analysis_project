# AE-32C Phase D — Exact-Commit Validation Prerequisite

## Purpose

Phase D prevents either AE-32C live workflow from making provider requests unless a successful, manually dispatched G9.42 validation record verifies the exact source commit being executed.

This gate applies to both:

- `AE-32C Live Evaluation (Manual)`
- `AE-32C Provider Compatibility Preflight (Manual)`

The provider preflight is a live provider request too; it is not exempt.

## Required operator input

When manually dispatching either workflow from `main`, provide the run ID of a successful **Manual Validation Dispatcher** run that used:

- target branch: `stage1/section-uuids`
- profile: `G9.42`
- regression mode: `profile`

The validation run must be completed successfully, not merely queued or in progress. Its artifact must still be available.

## Gate sequence

1. Confirm the validation run ID is numeric.
2. Retrieve its GitHub Actions run metadata using a read-only token.
3. Require a completed successful `workflow_dispatch` run from `main` using `.github/workflows/00_manual_validation_dispatcher.yml`.
4. Download the exact `manual-validation-evidence-<run-id>-<attempt>` artifact.
5. Verify the report's detached SHA-256, run/attempt, source commit, profile ID/hash, central validation-engine commit, test counts, and passing status.
6. Require the validation run's `head_sha` to match the recorded validation-engine commit.
7. Run the independent `verify_validation_evidence.py` verifier against the exact source and engine checkouts with `--require-pass`.
8. Run the independent provenance-catalog verifier, which checks the content-addressed evidence bundle.
9. Pass the exact validated source commit SHA to the provider job. The provider job checks out that SHA rather than resolving the development branch a second time.
10. Record the validation run ID/attempt, profile, engine commit, report digest, and bundle digest in the live run context.

Any missing artifact, invalid digest, mismatched commit, incorrect profile, incomplete test stage, failed test, or provenance verification error blocks the dependent provider job. The gate job does not receive provider secrets.

## Trust boundary

The gate binds a successful validation record to the current source commit and to the central validation workflow/engine commit. SHA-256 and catalog verification establish integrity and internal consistency, not an external digital signature or protection against compromise of the repository's trusted `main` branch.

A green G9.42 result validates the declared tests and their scope; it does not prove that the live diagnosis is causally correct. Live diagnosis quality still requires separate human review.

## Operator procedure

1. Apply the Phase D patch to `main` and `stage1/section-uuids` as mapped in `PATCH_MAP.md`.
2. Push the changes manually.
3. Dispatch **Manual Validation Dispatcher** from `main`, with branch `stage1/section-uuids`, profile `G9.42`, and regression mode `profile`.
4. Wait for the run to complete successfully. Save its run ID.
5. Dispatch the desired AE-32C live workflow from `main`, provide that validation run ID, select a provider, and explicitly confirm live calls.
6. If the source branch advances after validation, the gate rejects the stale run; validate the new source commit before retrying.

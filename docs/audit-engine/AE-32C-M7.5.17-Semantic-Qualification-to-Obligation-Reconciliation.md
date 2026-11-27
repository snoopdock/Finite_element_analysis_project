# AE-32C M7.5.17 — Semantic Qualification-to-Obligation Reconciliation

**Status:** Implemented; exact-source CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.16 — Semantic Evidence Qualification and Rule-Specific Adjudication  
**Authority:** derived per-obligation reconciliation only; no epistemic coverage or audit-decision authority

## 1. Purpose

M7.5.16 independently qualified each source-bound typed observation against a narrow, rule-specific semantic contract. It did not determine how multiple observations combine for a single evidence obligation, nor did it produce a complete per-obligation reconciliation.

M7.5.17 adds that missing layer. It first independently replays the M7.5.16 qualification result, then reconciles every evidence obligation in the verified M7.5.9 rule-derived plan. It records coverage-dimension obligations as `NOT_IN_SCOPE`; they are not reinterpreted as semantic evidence.

## 2. Explicit aggregation policy

The policy registry is versioned and digest-bound. It defines the same explicit aggregation rule separately for every currently supported rule/evidence contract:

`CONTESTED_THEN_UNKNOWN_THEN_ANY_SUPPORTED_ELSE_INSUFFICIENT`

For each evidence obligation:

| Condition | Reconciled disposition |
|---|---|
| No qualification rows exist | `UNKNOWN` |
| At least one row is `CONTESTED` | `CONTESTED` |
| Otherwise, at least one row is `UNKNOWN` | `UNKNOWN` |
| Otherwise, at least one row is `SUPPORTED` | `SUPPORTED_WITHIN_CONTRACT` |
| Otherwise, all rows are `INSUFFICIENT` | `INSUFFICIENT` |

An `INSUFFICIENT` observation is not treated as counterevidence to a separate supported observation. It remains listed in the reconciliation. A `CONTESTED` or `UNKNOWN` observation prevents the aggregate from being reported as supported. This is an explicit conservative policy, not a claim that the observation set is exhaustive.

The result retains the IDs and states of all contributing observations so that the aggregation is inspectable.

## 3. Replay and binding requirements

The public reconciliation API requires:
- The M7.5.16 qualification result and original typed-evidence observation bundle.
- The `AssuranceClaim`, verified `RuleCoveragePlan`, and coverage manifest.
- The exact source snapshot manifest and repository root.
- The defeater records supplied to M7.5.16, if any.

It calls `verify_semantic_evidence_qualification(...)` before aggregation. Therefore, a caller cannot submit a self-digested but semantically altered qualification result. The reconciliation also checks that each row belongs to an expected evidence obligation, that its rule/evidence-kind binding matches the obligation ID, and that no observation is duplicated for the same obligation.

Every evidence obligation in the verified plan receives a disposition. An expected obligation with no observation or qualification row is explicitly `UNKNOWN`; absence is not converted into a negative finding.

## 4. Separation from epistemic coverage

M7.5.17 deliberately does **not** map `SUPPORTED_WITHIN_CONTRACT` to `ObligationDisposition.EVIDENCE_BOUND`. The latter belongs to the separate epistemic evidence-assertion and freshness model. A narrow validator result is not itself a persisted `EvidenceAssertion`.

Consequently:
- The input coverage manifest is not modified.
- No coverage dossier is created, rewritten, or upgraded.
- No epistemic assertion is created.
- Coverage-dimension obligations are reported as `NOT_IN_SCOPE` by this reconciliation.
- The result does not claim that all rule obligations are satisfied.

The derived reconciliation is content-addressed and independently replayable. It is not a persistent ledger in this milestone.

## 5. Public API

Module: `audit_engine/semantic_audit/epistemic/qualification_reconciliation.py`

- `QualificationReconciliationError`
- `qualification_aggregation_policy_registry()`
- `reconcile_semantic_qualifications(...)`
- `verify_qualification_obligation_reconciliation(...)`

The API is exported from `audit_engine.semantic_audit.epistemic`.

## 6. Structural, behavioral, and adversarial tests

The dedicated tests cover:
- Policy registry schema and digest.
- One and multiple supported observations for a single obligation.
- A contested observation taking precedence over another supported observation.
- Missing qualification remaining `UNKNOWN`.
- Unsupported external-model evidence remaining `UNKNOWN`.
- Graph imports remaining `INSUFFICIENT` for service non-use.
- Coverage obligations remaining outside this semantic reconciliation.
- Independent reconciliation replay and source-drift rejection.
- Reconciliation digest tampering rejection.
- Duplicate obligation/observation pair rejection, including repeated obligation bindings in a single observation.
- Missing historical source-file handling, normalized to `QualificationReconciliationError` rather than leaking a raw filesystem exception.
- Explicit no-mutation/no-authority fields in the output.

## 7. Explicit limitations

M7.5.17 does not:
1. Establish that the rule selection, source inventory, or observation set is universally exhaustive.
2. Treat a supported narrow contract as proposition-wide truth.
3. Resolve unknown or contested evidence.
4. Turn insufficient evidence into negative evidence.
5. Convert narrow support into an epistemic assertion or `EVIDENCE_BOUND` coverage disposition.
6. Mutate M7.5.8 manifests, M7.5.10 dossiers, or any epistemic/assurance store.
7. Reconcile coverage-dimension obligations or execution completeness; those remain governed by their earlier layers.
8. Grant `ALLOW`/`DENY`, audit-gate authorization, release approval, or production approval.
9. Provide a persistent reconciliation ledger, external trust anchor, or atomic cross-store transaction.

## 8. CI validation

Workflow: [M7.5.17 qualification reconciliation](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_17_qualification_reconciliation.yml)

Exact-source run, tested revision, dedicated test count, M7.5.16 regression count, complete M7.5 regression count, and compilation result will be recorded after CI completes against the final branch head.

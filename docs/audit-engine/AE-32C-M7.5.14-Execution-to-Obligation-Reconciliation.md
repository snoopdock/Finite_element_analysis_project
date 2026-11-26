# AE-32C M7.5.14 — Execution-to-Obligation Reconciliation

**Status:** Implemented; exact-source CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.13 — Extractor Execution Evidence and Result Reconciliation  
**Authority:** dossier-bound reconciliation of execution accounting; no semantic-evidence or audit-decision authority

## 1. Purpose

M7.5.13 proves that each declared extractor candidate received an execution outcome. M7.5.14 connects that report to a specific M7.5.10 coverage dossier and the M7.5.9 rule-derived obligation universe.

This is an extension record. It does not rewrite an existing dossier, replace its manifest, add assertions to the epistemic ledger, or upgrade the epistemic coverage result.

## 2. Reconciliation semantics

For rule-derived obligations:

- `coverage:python_ast` and `coverage:workflow_static_scan` are reported as `EXTRACTOR_EXECUTION_COMPLETE` only when every candidate for that extractor in the verified inventory has an `EXECUTED` outcome.
- A missing candidate set remains `UNKNOWN`; failed, limited, unsupported, missing, or explicitly excluded candidates prevent execution-complete status.
- `coverage:source_manifest` is reported as `MANIFEST_VERIFIED_WITHIN_DECLARED_INVENTORY` after semantic verification of the source/extractor inventory.
- Every `evidence:<kind>` obligation remains `UNKNOWN`. Generic AST or lexical scanner output is not silently converted into typed evidence such as an external-model-response intake, graph import, or workflow command finding.

These statuses describe execution and manifest accounting only. They do not mean that an obligation has been semantically satisfied.

## 3. Dossier binding and persistence

The builder requires:

1. A valid M7.5.9 plan and corresponding M7.5.8 manifest.
2. A semantically verified M7.5.12 inventory and independently replayed M7.5.13 execution report.
3. A matching M7.5.10 dossier whose semantics and current-store replay verify.
4. Matching source-snapshot identities throughout.

The reconciliation is persisted in a separate append-only SQLite hash-chain ledger. It is keyed by its canonical reconciliation digest, supports idempotent writes, rejects conflicting identities, and exposes integrity/history/read operations. The original dossier remains unchanged.

## 4. APIs

Module: `audit_engine/semantic_audit/epistemic/execution_obligation_reconciliation.py`

- `ExecutionObligationReconciliationError`
- `ExecutionObligationReconciliationStore`
- `build_execution_obligation_reconciliation(...)`
- `build_and_persist_execution_obligation_reconciliation(...)`
- `verify_execution_obligation_reconciliation(...)`

## 5. Tests

Structural and behavioral tests cover:
- Extractor execution completeness versus typed evidence UNKNOWN.
- Exact semantic replay from the append-only reconciliation ledger.
- Source-content drift rejection.
- Missing dossier rejection.
- Rehashed ledger tampering rejection.
- Dossier-manifest identity mismatch rejection.

## 7. Exact-source CI validation

Workflow: [45910913764](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45910913764)

- Validated source revision: `d5b5422eee6ba79cd66751e14ca4db90eb839a4e`
- Runtime: Ubuntu 24.04, Python 3.11
- Epistemic package compilation: passed
- Dedicated M7.5.14 tests: 7 passed
- Complete M7.5 regression: 148 passed
- Job ID: `140218772228`
- Final job conclusion: success

The first run exposed a real ledger-verification defect: the append-only event hash chain could be recomputed after changing the payload while leaving the reconciliation's own content digest unchanged. The verifier now checks both the event chain and the embedded reconciliation identity/digest. Follow-up tests also verify idempotent recording, append-only SQL protections, and restart recovery.

## 8. Limitations

M7.5.14 does not:
1. Prove universal source, extractor, rule, or obligation exhaustiveness.
2. Convert extractor output into typed semantic evidence or assertions.
3. Establish that AST/lexical observations satisfy a rule's semantic evidence requirements.
4. Resolve gaps or change existing coverage dispositions.
5. Mutate or upgrade an M7.5.10 dossier or its epistemic result.
6. Establish proposition truth, graph completeness, ALLOW/DENY, audit-gate authorization, or production approval.
7. Provide atomic transactions across the source, assurance, epistemic, dossier, and reconciliation stores.
8. Establish an external trust anchor for the append-only hash chain.

Exact-source CI validation details will be appended after the workflow runs against the resulting branch head.

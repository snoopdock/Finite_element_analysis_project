# AE-32C M7.5.4 — Exact-source validation record

**Result:** SUCCESS  
**Workflow:** [45898608483](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45898608483)  
**Branch:** `stage1/section-uuids`  
**Exact tested source SHA:** `3c2a1a2f76b9bf8520d3e7b3d245d8768b038ad0`  
**Workflow file:** `.github/workflows/m7_5_epistemic_contracts.yml`  
**Artifact:** [m7-5-epistemic-validation-45898608483-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45898608483/artifacts/15153624492)  
**Artifact digest:** `sha256:5e210a78ba7543a6b282fedca21766c87c781f235838361926b50f31e6f9e41b`

## Exact-source results

| Suite | Tests | Result |
|---|---:|---|
| M7.5.1 contracts | 14 | Passed |
| M7.5.2 persistence | 9 | Passed |
| M7.5.3 completeness and negative-claim admissibility | 14 | Passed |
| M7.5.4 provenance, freshness and invalidation | 12 | Passed |
| **Total** | **49** | **Passed** |

Additional results:
- Python 3.11 package compilation passed.
- M7.5.2 and M7.5.3 SQLite migration tests passed.
- Provenance DAG cycle rejection passed.
- Claim and evidence dependency manifests passed exact-set validation.
- Transitive invalidation, sibling isolation and idempotent replay passed.
- Failure-injection tests confirmed that dependency registration and multi-node invalidation roll back atomically at the event limit.
- Tampered event history was rejected before freshness could be asserted or invalidation could be recorded.
- All workflow steps and artifact upload succeeded.

## Correction history

Intermediate CI attempts found and corrected:
1. Python import-line formatting introduced during package export updates.
2. The fresh-database SQLite CHECK constraint had not been extended to the new provenance event types.
3. A completeness claim's direct dependency manifest initially included evidence-node edges; manifests are now emitted per dependent node.
4. The tampering test fixture needed to commit its direct SQL mutation before opening a new read transaction.

These earlier failed runs are not counted as validation. The successful exact-source run above is the acceptance evidence for this tranche.

## Assurance boundary

This run validates the local contracts, SQLite event schema migration, append-only dependency graph, cycle rejection, closed-manifest matching, deterministic transitive invalidation, freshness gating, and tested atomic rollback behavior.

It does not establish that dependency declarations are semantically exhaustive, that source-change notifications are authenticated or complete, that expected revisions are checked against a trusted live registry, or that invalidation is automatically triggered by every external change. It does not establish proposition truth, audit-gate integration, production durability, external tamper resistance or production approval.

M7.5.4 is implementation-validated within this bounded scope only.

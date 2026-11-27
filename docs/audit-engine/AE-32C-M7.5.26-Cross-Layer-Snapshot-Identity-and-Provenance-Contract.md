# AE-32C M7.5.26 — Cross-Layer Snapshot Identity and Provenance Contract

**Status:** Implemented and CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.25 — Cross-Store Consistency and Failure-Injection Audit  
**Scope:** bind persisted execution and semantic-qualification artifacts to one source snapshot, distinguishing declared identity from independently replayed source state.

## 1. Problem statement

M7.5.14 and M7.5.17 carry matching source snapshot, claim, plan, and coverage identifiers. M7.5.18 stores qualification, observation-bundle, and reconciliation digests with an eight-field currentness context. M7.5.24 retrieves and replays persisted records and composes them. M7.5.25 narrows selected time-of-check/time-of-use windows.

Those mechanisms establish content bindings and bounded replay observations. Matching identifiers alone do not establish that every artifact was independently derived from the same Git tree.

M7.5.26 distinguishes:

1. **Declared identity:** artifact content seals verify and cross-layer identifiers match.
2. **Source-state replay:** the Git-backed source manifest is independently replayed against a supplied checkout; commit, root tree, inventory, and clean-worktree state match.
3. **Atomic cross-store snapshot:** a globally consistent transaction across all participating stores. This milestone does not provide it.

## 2. Implementation

### 2.1 Source-manifest replay helper

`tools/ae32c_source_snapshot_manifest.py` adds `verify_verified_manifest_data(...)`. It validates the manifest seal, source/inventory bindings, verified postflight state, and clean materialization metadata, then reconstructs the Git snapshot using the recorded event context. It is non-mutating and requires an already VERIFIED manifest.

External Git LFS payload bytes and recursive submodule contents remain outside the helper's verification scope.

### 2.2 Cross-layer contract

New module: `audit_engine/semantic_audit/epistemic/cross_layer_snapshot_provenance.py`

Public APIs:

- `CrossLayerSnapshotProvenanceError`
- `verify_cross_layer_snapshot_provenance(...)`
- `verify_cross_layer_snapshot_provenance_envelope(...)`

The verifier checks source-manifest, execution reconciliation, qualification reconciliation, qualification, observation-bundle, composition, and orchestration seals and cross-bindings. It checks common source snapshot, claim, plan, and coverage identifiers; exact source-manifest binding from execution reconciliation; and the M7.5.24 replay/bracket references.

### 2.3 Assurance levels

Without `repository_root`, the result explicitly reports `snapshot_identity_assurance = DECLARED_ONLY` and `source_state_verification.status = NOT_PERFORMED`.

With `repository_root`, the verifier reconstructs the Git-backed source state and reports `SOURCE_STATE_REPLAY_VERIFIED`. A replay failure raises; it is not silently downgraded.

The envelope checker validates only the provenance envelope's content seal. It does not replay the repository or persisted stores.

## 3. Failure behavior and tests

Dedicated tests cover declared-only versus replayed status, post-capture repository mutation, cross-artifact snapshot mismatch, execution-to-manifest mismatch, manifest tampering, orchestration tampering, missing bundle provenance, and envelope mutation.

The tests use a temporary Git repository with a real commit/tree and a source manifest captured and postflight-verified by the existing source snapshot utility.

## 4. Limitations and authority boundaries

A successful result means the supplied artifact graph is internally sealed and bound to one declared source snapshot. When source-state replay is requested and succeeds, it additionally means the checkout reproduced the source manifest's Git commit/tree/inventory and clean-worktree observation at replay time.

It does not establish an atomic read across SQLite stores, prevent later mutations, authenticate artifact producers, verify external LFS payload bytes or recursive submodule contents, or prove graph completeness. It does not establish evidence acceptance, proposition truth, assurance success, ALLOW/DENY, audit authorization, release approval, or production approval.

The source manifest's `atomic_repository_snapshot_established` remains false; the cross-layer result preserves `atomic_cross_store_snapshot = false` and `trust_anchor = NONE`.

## 5. Validation

Workflow: [M7.5.26 Cross-Layer Snapshot Provenance](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45973681537)

- Exact tested implementation revision: `21e282d9c6dd5816fc3c6d15570a2bdd7c018052`.
- Python 3.11 compilation: passed.
- M7.5.26 dedicated structural/adversarial tests: 9 passed.
- Source snapshot manifest regression: 8 passed.
- M7.5.24 orchestration regression: 9 passed.
- M7.5.25 failure-injection regression: 3 passed.
- Complete M7.5 regression: 261 passed.

The workflow completed successfully. The exact tested revision includes the full-envelope seal correction after the first run identified a test gap. The documentation status update is a documentation-only follow-up; the workflow path filter causes the final documentation revision to be revalidated.

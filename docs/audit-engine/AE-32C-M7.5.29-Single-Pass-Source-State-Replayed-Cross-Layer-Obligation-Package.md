# AE-32C M7.5.29 — Single-Pass Source-State-Replayed Cross-Layer Obligation Package

**Status:** Implemented; implementation and regression CI-validated; documentation-only exact-head revalidation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.28 — Source-State Replay Consumer Requirements and Integration Design  
**Implementation baseline:** `f73d80ef526a2d5811a800bdae4943941c61bd41`  
**Scope:** add an opt-in strict package API at the existing M7.5.24 orchestration boundary  
**Authority:** provenance/package integrity only; no audit decision or release authority

## 1. Implementation summary

M7.5.29 implements the package topology approved in M7.5.28.

The existing M7.5.24 orchestration operation is factored into a private single-pass implementation helper. The existing public `verify_persisted_cross_layer_obligation_composition(...)` remains the compatibility API and returns the same v1 orchestration envelope. The new `verify_persisted_cross_layer_obligation_package(...)` invokes that same helper once and receives the exact objects retrieved and used during the operation.

The package operation does not re-fetch execution or qualification records to construct provenance. It passes the in-process objects to M7.5.26:
- verified source snapshot manifest;
- retrieved execution reconciliation;
- retrieved qualification reconciliation;
- current semantic qualification;
- current typed observation bundle;
- actual sealed orchestration result; and
- the same repository checkout root.

The new operation is explicit opt-in. Existing v1 callers do not acquire a stronger source-state guarantee merely by continuing to use the old API.

## 2. API and package shape

New API:

`verify_persisted_cross_layer_obligation_package(...)`

New package schema:

`ae32c/cross-layer-obligation-package/v1`

The package contains:
- `orchestration`: unchanged M7.5.24 v1 result and its existing `orchestration_sha256`;
- `provenance`: M7.5.26 full-verifier result and its `cross_layer_snapshot_identity_sha256`;
- `atomic_cross_store_snapshot = false`;
- `trust_anchor = NONE`;
- explicit false authority fields and `downstream_authorization = NOT_EVALUATED`;
- outer `package_sha256`.

The seal order is acyclic:

1. M7.5.24 seals its orchestration result.
2. M7.5.26 binds that result to the source manifest and cross-layer artifacts, then performs source-state replay.
3. The package seals the unchanged orchestration and provenance envelopes together.

The expected source revision is taken only from the verified manifest's `source.commit_oid`. The strict API does not accept a caller-selected alternative revision.

## 3. Strict source-state replay

Package creation always invokes `verify_cross_layer_snapshot_provenance(..., repository_root=...)`.

Creation fails closed if:
- the source manifest is absent, malformed, unverified, or incorrectly sealed;
- the repository checkout is stale, dirty, or differs in commit, root tree, or source inventory;
- cross-layer artifact bindings or the orchestration envelope fail verification;
- the source-state verifier raises; or
- the returned assurance level is not exactly `SOURCE_STATE_REPLAY_VERIFIED`.

There is no `DECLARED_ONLY` fallback in this package API.

The source-state check is a point-in-time reconstruction of the manifest's Git commit, root tree, inventory and clean-worktree state. It is not an atomic transaction with the independent SQLite stores.

## 4. Qualification currentness remains a separate axis

The package preserves the M7.5.24 qualification currentness result without promotion:
- `CURRENT_REPLAY_VERIFIED`; or
- `BLOCKED_INVALIDATED`.

A successful source-state replay does not promote an invalidated qualification. The package verifier checks that the M7.5.26 currentness field agrees with the embedded M7.5.24 composition.

## 5. Envelope-only verification

New API:

`verify_cross_layer_obligation_package_envelope(...)`

It checks:
- outer package schema and digest;
- inner M7.5.24 orchestration seal and composition seal;
- inner M7.5.26 provenance content seal;
- required source-state assurance label;
- orchestration/provenance and qualification-currentness bindings;
- non-atomicity, trust-anchor, and non-authority fields.

It does **not** replay Git state, read SQLite stores, or perform semantic replay. Its result explicitly reports:

`source_state_replay_performed_by_this_check = false`

A fresh source-state replay requires rerunning the package-producing operation with live stores, artifacts and checkout.

## 6. Tests added

`tests/semantic_graph/test_m7529_source_state_replayed_cross_layer_package.py` covers:

1. Real M7.5.26 Git source-state replay through the new package API.
2. Exact object identity passed from the single-pass M7.5.24 context to M7.5.26.
3. Exactly one retrieval from each persisted reconciliation store.
4. Execution replay ordering and the existing pre/post qualification bracket.
5. Dirty-worktree rejection.
6. Changed-commit rejection.
7. Rejection of a resealed `DECLARED_ONLY` package.
8. Preservation of `BLOCKED_INVALIDATED` qualification currentness.
9. Outer package, inner orchestration, and inner provenance tampering.
10. Missing persisted record failure before provenance replay.

The M7.5.26 test fixture supplies a real temporary Git repository and verified manifest. Existing M7.5.24–M7.5.28 and source-manifest regressions remain in the dedicated workflow.

## 7. Explicit assurance limits

This package does not establish:
- atomicity or a globally linearizable snapshot across SQLite stores;
- immutable state after replay;
- producer or consumer authentication;
- external Git LFS payload-byte verification;
- recursive submodule content verification;
- graph completeness, evidence acceptance, or proposition truth;
- solver certificate correctness or encoding correspondence;
- LLM evidence support or authorization;
- repair safety or correctness of an actual source patch;
- termination, fixed point, or empirical improvement;
- ALLOW/DENY, audit authorization, release approval, or production approval.

The uploaded architecture notes remain applicable:
- LLM outputs are advisory and cannot turn ABSTAIN/HOLD into ALLOW;
- remediation must be checked against the actual source patch, not only an abstract plan;
- solver status/certificates must bind to exact formal instances, with encoding correctness separate from solver correctness;
- source-state identity does not establish termination, convergence, fixed point, or quality improvement.

No distributed transaction, external trust anchor, universal consumer interception, or authority expansion is introduced.

## 8. Validation record

Implementation validation evidence:
- [M7.5.29 workflow run 45985247648](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45985247648) — success on implementation revision `7f231ae83a59bc91e6aaba120eedfad3ef8de9c1`; exact triggering SHA checkout.
- M7.5.29 package tests: 9 passed.
- M7.5.28 design-contract tests: 8 passed.
- M7.5.27 consumer inventory tests: 6 passed.
- M7.5.26 provenance behavioral tests: 9 passed.
- M7.5.24 orchestration regression: 9 passed.
- M7.5.25 failure-injection regression: 3 passed.
- Source snapshot manifest regression: 8 passed.
- Complete M7.5 regression: 284 passed.
- Python 3.11 compilation: passed.

The two documentation updates in this commit are included in the M7.5.29 workflow path filters. The workflow checks out `${{ github.sha }}`; its subsequent success is required to establish exact-head validation of this documentation revision.

Do not treat this milestone as CI-validated until the final run is successful and its checked-out SHA equals the final `stage1/section-uuids` head.

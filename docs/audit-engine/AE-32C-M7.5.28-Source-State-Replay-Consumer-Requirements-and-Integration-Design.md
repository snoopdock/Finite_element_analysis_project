# AE-32C M7.5.28 — Source-State Replay Consumer Requirements and Integration Design

**Status:** Design completed; exact-head design and regression CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.27 — Cross-Layer Provenance Consumer Inventory and Enforcement Boundaries  
**Baseline revision:** `fa62909719665bbc97b2824a1b868b0c1a4807e1`  
**Scope:** identify one justified source-state replay consumer, define its contract, and resolve package/seal topology before production integration  
**Authority:** integration design only; no production behavior or authority change

## 1. Decision

The one justified integration candidate is the **M7.5.24 persisted cross-layer obligation orchestrator**.

It is an actual operation, not a hypothetical downstream consumer. It:
- retrieves persisted M7.5.14 execution reconciliation and M7.5.18 qualification reconciliation;
- receives the source snapshot manifest, rule-derived plan, coverage manifest, current semantic qualification, and typed observation bundle;
- has the target `repository_root`;
- replays execution reconciliation through M7.5.14;
- invokes the currentness-gated qualification consumer from M7.5.21;
- brackets qualification replay with a second execution replay; and
- composes the actual operation results.

The orchestrator is therefore the narrowest existing boundary that has all six artifacts required by M7.5.26 and the repository checkout needed for source-state replay. The candidate is not the graph snapshot workflow, which already performs source-manifest preflight and postflight around graph projection. Nor is it every assurance, dossier, solver, LLM, or repair consumer.

**M7.5.28 does not wire the integration.** It establishes the requirements and a versioned package design. Implementation is a separate M7.5.29 change, subject to these constraints.

## 2. Why M7.5.24 is a real gap boundary

M7.5.14 replays extractor execution against the source inventory and reads the corresponding source bytes from `repository_root`. This is an execution replay of the declared extractor workload. It is not by itself a reconstruction of the complete Git commit, root tree, inventory, and clean-worktree state.

M7.5.21 checks eight currentness dimensions, including source snapshot identity, plan, registries, coverage, qualification, and observation bundle. Its currentness checks compare supplied live artifact context; they do not independently reconstruct the complete Git source state.

M7.5.24 composes those results and already has the repository checkout. It is the correct place to offer a stronger, separately typed package that adds the M7.5.26 full source-state replay and cross-artifact binding.

The source/graph snapshot workflow is different: it already runs source-manifest verification before graph projection and again after projection in the same workflow job. M7.5.28 does not add a second provenance gate to that workflow.

## 3. Consumer contract

### 3.1 Operation and required inputs

The proposed package-producing operation is:

`verify_persisted_cross_layer_obligation_package(...)`

It must use the same single-pass operation context as M7.5.24 and must not retrieve or replay the persisted records a second time merely to construct the package.

The context must include:
1. Verified source snapshot manifest.
2. Persisted execution reconciliation retrieved by its exact record ID.
3. Persisted qualification reconciliation retrieved by its exact record ID.
4. Current semantic qualification.
5. Current typed observation bundle.
6. Actual M7.5.24 orchestration result, including the execution replay bracket and qualification consumer result.
7. Repository checkout root used by the operation.

The expected source revision is taken from the verified source manifest's `source.commit_oid`. The package operation must not accept a second, caller-selected revision that could silently redefine the manifest's target.

### 3.2 Assurance policy

Package creation is strict:

- It invokes `verify_cross_layer_snapshot_provenance(..., repository_root=...)`.
- It requires `snapshot_identity_assurance = SOURCE_STATE_REPLAY_VERIFIED`.
- It does not fall back to `DECLARED_ONLY` if the checkout is missing, dirty, stale, or inconsistent.
- Replay errors abort package creation.
- The resulting M7.5.26 source-state replay remains a point-in-time observation.

The existing M7.5.24 API remains available with its existing v1 contract. It must not silently gain a stronger guarantee or change its result shape. The new package API is the explicit opt-in operation for consumers that require source-state replay.

### 3.3 Preserve qualification currentness independently

Source-state replay and qualification currentness are different axes.

The package must preserve the actual M7.5.24 qualification currentness outcome:
- `CURRENT_REPLAY_VERIFIED`, or
- `BLOCKED_INVALIDATED`.

A package may carry a successfully replayed Git source state while qualification is `BLOCKED_INVALIDATED`. That package is not a qualification success. Consumers must inspect both axes and may not infer current semantic qualification from source-state replay.

## 4. Package and digest topology

A direct embedding of the provenance envelope inside the already sealed M7.5.24 orchestration result is invalid: M7.5.26 hashes the orchestration result, while adding that provenance envelope would change the orchestration hash and therefore invalidate the envelope. Attempting to make each seal include the other creates a circular dependency.

The implementation must use an acyclic, nested package:

```text
M7.5.24 orchestration core
  └── orchestration_sha256
        │
        ▼
M7.5.26 provenance envelope
  └── cross_layer_snapshot_identity_sha256
        │
        ▼
cross-layer obligation package
  └── package_sha256
```

Proposed schema:

```json
{
  "schema": "ae32c/cross-layer-obligation-package/v1",
  "orchestration": {
    "...": "unchanged M7.5.24 v1 result",
    "orchestration_sha256": "..."
  },
  "provenance": {
    "...": "M7.5.26 full verifier result",
    "cross_layer_snapshot_identity_sha256": "..."
  },
  "package_sha256": "..."
}
```

Hashing order:
1. M7.5.24 seals its existing orchestration payload exactly as it does today.
2. M7.5.26 verifies the source manifest, execution reconciliation, qualification reconciliation, qualification, observation bundle, and sealed orchestration result; it independently replays the source state.
3. The package layer seals the pair of the unchanged orchestration result and the M7.5.26 provenance result.
4. The package digest is never an input to either inner digest.

The existing `verify_orchestrated_obligation_composition(...)` remains a v1 orchestration-envelope checker. A new package-envelope checker must verify the package digest, inner orchestration envelope, and M7.5.26 content seal. It must report that it checked content binding only; it must not claim a fresh repository replay. Fresh replay requires rerunning the package-producing operation with live stores, artifacts, and checkout.

## 5. Single-pass integration requirement

The current M7.5.24 function owns the authoritative in-process objects produced or retrieved during the operation. M7.5.29 must avoid a second independent retrieval that could observe a different state.

The preferred implementation structure is:
- factor the existing M7.5.24 operation into a private single-pass helper;
- have the existing public v1 API call that helper and return the unchanged v1 result;
- have the new package API call the same helper once, receive the exact artifacts and replay results used, invoke M7.5.26 on those objects, and build the outer package;
- preserve existing exception semantics or map new source-state replay errors to a specific package error without downgrading them;
- leave independent SQLite stores independent; the package is not a distributed transaction.

No caller-supplied replay-result mappings may be accepted. No second read of the stores is permitted solely to construct the provenance envelope.

## 6. Package consumer requirements

A downstream consumer of the package must declare its actual requirement.

| Consumer purpose | Required handling |
|---|---|
| Display or inspect a legacy M7.5.24 result | Existing v1 orchestration verifier; no source-state claim |
| Inspect declared cross-layer bindings only | M7.5.26 `DECLARED_ONLY` may be displayed as declared-only; it is not this strict package |
| Consume the strict cross-layer package as a source-state-replayed package | Verify package and inner seals; require `SOURCE_STATE_REPLAY_VERIFIED`; inspect qualification currentness separately |
| Require a fresh source-state replay now | Rerun the package-producing operation with live inputs and checkout; a stored package seal is insufficient |
| Require atomic cross-store consistency | Not supported by this package |
| Authenticate producers or consumers | Not supported; requires a separately specified trust anchor/signature and identity model |
| Authorize evidence acceptance, proposition truth, audit decisions, release, or production | Not supported; package authority remains non-authorizing |

No universal interception layer is proposed. Only a consumer that explicitly requires the strict package should call the new package API.

## 7. Failure behavior

Package creation must fail closed for:
- missing or malformed source manifest;
- invalid source-manifest seal or non-VERIFIED manifest;
- Git commit, root tree, inventory, or clean-worktree mismatch;
- missing or malformed execution/qualification records;
- any cross-artifact snapshot, plan, claim, coverage, bundle, or composition mismatch;
- invalid execution replay bracket;
- qualification consumer identity mismatch;
- M7.5.26 full-verifier exception;
- package seal construction or verification failure.

A `BLOCKED_INVALIDATED` qualification outcome is preserved as a valid observed outcome, not converted into success. Whether a later business operation may proceed remains outside this package contract.

No silent downgrade to `DECLARED_ONLY` is allowed by the strict package API.

## 8. Assurance and authority limits

The package establishes content binding and, when built successfully, that the supplied checkout reproduced the manifest's Git commit/tree/inventory and clean-worktree state at replay time.

It does not establish:
- atomicity across execution, qualification, consumer-check, dossier, assurance, or epistemic SQLite stores;
- immutability after replay or prevention of later mutation;
- artifact producer or consumer authentication;
- external Git LFS payload-byte verification;
- recursive submodule content verification;
- graph completeness or semantic evidence sufficiency;
- proposition truth or formal theorem validity;
- solver certificate correctness or encoding-to-repository correspondence;
- LLM evidence support, model reliability, or authorization;
- repair safety or correctness of an actual source patch;
- termination, fixed point, or empirical improvement;
- ALLOW/DENY, audit authorization, release approval, or production approval.

Required fields remain:
- `atomic_cross_store_snapshot = false`;
- `trust_anchor = NONE`;
- all M7.5.26 authority flags false;
- `downstream_authorization = NOT_EVALUATED`.

The uploaded architecture notes 003–006 reinforce the separation of deterministic authority from LLM advice, the requirement to verify actual source patches, binding solver certificates to exact formal instances, and distinguishing source-state identity from termination or improvement claims. The package is provenance evidence only; it does not substitute for those separate contracts.

## 9. M7.5.29 implementation acceptance criteria

1. Existing M7.5.24 v1 callers receive byte-for-byte equivalent canonical result content for unchanged inputs.
2. New package API uses one retrieval/replay pass and exactly the artifacts used by M7.5.24.
3. The package always requests source-state replay and rejects dirty/stale/mismatched checkout state.
4. `DECLARED_ONLY` cannot be returned by the strict package API.
5. The package preserves `CURRENT_REPLAY_VERIFIED` versus `BLOCKED_INVALIDATED` without promotion.
6. The orchestration core, provenance envelope, and outer package seals are acyclic and independently tamper-detectable.
7. A modified package field, inner orchestration field, or provenance field is rejected.
8. A package-envelope-only check explicitly reports that source-state replay was not performed by that check.
9. Replaying a stored package requires live operation inputs; a content seal alone is not called semantic replay.
10. Failure injection covers source mutation, dirty worktree, missing stores, invalidation between checks, package tampering, and store changes around the operation.
11. No distributed transaction, external trust anchor, or authority expansion is introduced.
12. Existing M7.5.21–M7.5.27 regressions remain green.

## 10. Files and validation

M7.5.28 adds:
- `tests/semantic_graph/test_m7528_source_state_replay_consumer_design.py`
- this design record;
- a dedicated exact-triggering-revision workflow.

No production Python implementation is changed in M7.5.28.

The design tests inspect:
- whether M7.5.24 has the required candidate context;
- whether M7.5.26 accepts the exact artifacts and repository root;
- the proposed acyclic seal topology and tamper behavior;
- strict source-state replay semantics in M7.5.26 and the source manifest helper;
- the existing graph snapshot pre/post verification boundary;
- absence of premature M7.5.26 wiring into M7.5.24; and
- the documented non-authority and M7.5.29 implementation requirements.

Validation evidence:
- [M7.5.28 workflow run 45983543634](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45983543634) — success on design/test revision `58a511475c4a0a261ceaf4d318d94d91ed064edb`.
- M7.5.28 design tests: 8 passed.
- M7.5.27 consumer inventory regression: 6 passed.
- M7.5.26 provenance behavioral regression: 9 passed.
- M7.5.24 persisted orchestration regression: 9 passed.
- M7.5.25 cross-store failure-injection regression: 3 passed.
- Source snapshot manifest regression: 8 passed.
- Complete M7.5 regression: 275 passed.
- Python 3.11 compilation: passed.

The workflow checked out the exact triggering revision. This documentation-only validation update is included in the workflow path filter and is revalidated on the resulting final branch head.

## 11. Next milestone

**M7.5.29 — Single-Pass Source-State-Replayed Cross-Layer Obligation Package.**

M7.5.29 may implement only the versioned package API and the private single-pass orchestration refactor described here. It must preserve M7.5.24 v1 compatibility and all authority/atomicity limitations. It must not add any other downstream consumers.

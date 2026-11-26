# AE-32C M7.5.4 — Provenance dependencies, freshness and deterministic invalidation

**Status:** IMPLEMENTED AND CI-VALIDATED (exact-source run 45898608483)  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.1 epistemic contracts; M7.5.2 append-only persistence; M7.5.3 scope-bound completeness  
**Authority:** provenance lifecycle and freshness reporting only; no proposition-truth inference or decision-gate authority

## 1. Objective

M7.5.3 established scoped completeness contracts and negative-claim admissibility preconditions. It did not provide a persistent mechanism for determining whether a claim's source snapshot, enumerator, verification method or evidence provenance had changed since the claim was assessed.

M7.5.4 adds an append-only provenance dependency graph, explicit dependency manifests, deterministic transitive invalidation and a fail-closed freshness result.

The dependency direction is explicit: a **dependent node relies on a dependency node**. If a dependency changes, all transitive dependents are invalidated. The changed root is not itself marked stale by this propagation operation.

## 2. Contracts

New immutable contracts in `audit_engine.semantic_audit.epistemic.contracts`:

- `ProvenanceDependency`: stable edge ID, dependent node ID, dependency node ID, dependency kind and expected revision.
- `ProvenanceManifest`: node ID, exact set of dependency edge IDs and manifest version.
- `ProvenanceInvalidation`: invalidation ID, affected node, root change ID, changed dependency, reason and observation time.
- `FreshnessStatus`: `FRESH`, `INVALIDATED`, `UNKNOWN`.
- `FreshnessResult`: node ID, status, invalidation history references and reason.

Self-dependencies are rejected. All identity and version fields are non-empty. Dependency edges are immutable records.

## 3. Persistent dependency graph

The SQLite event ledger now supports `dependency`, `dependency_manifest` and `invalidation` event types in addition to assertions, gaps and completeness claims.

Public store operations:
- `record_dependency(edge)`
- `record_completeness_dependencies(claim)`
- `record_dependency_manifest(manifest)`
- `dependency_history()`
- `invalidate_dependency(changed_node_id, root_change_id=..., reason=..., observed_at=...)`
- `invalidation_history(node_id)`
- `freshness_status(node_id)`

### 3.1 Claim dependency binding

`record_completeness_dependencies(claim)` declares edges from the claim node to:
- its source snapshot;
- its enumeration method and version;
- its verification method;
- each evidence reference.

Each evidence node is also linked to its source snapshot, producer, method and optional artifact digest.

The helper appends the edge set and a closed dependency manifest in one SQLite transaction. Repeating the same operation is idempotent. If an expected dependency is already invalidated, registration fails closed.

### 3.2 Cycle prevention

Before an edge is appended, the current directed dependency graph is checked for reachability from the proposed dependency back to the proposed dependent. An edge that would create a directed cycle is rejected before the append. The graph is therefore a DAG for edges admitted through this API.

The check and append execute under a SQLite write transaction to avoid concurrent writers introducing a cycle between validation and insertion.

### 3.3 Closed manifests and freshness

A node is `FRESH` only if:
1. it has a dependency manifest;
2. the manifest's edge IDs exactly match all currently recorded outgoing dependency edges for that node; and
3. no invalidation event exists for that node.

A node is `INVALIDATED` if at least one invalidation event exists.

A node is `UNKNOWN` if no manifest establishes the declared dependency set, or if the manifest does not match the recorded edges. Merely having no invalidation event is not sufficient to report freshness.

Adding an edge after a manifest makes freshness `UNKNOWN` until a new controlled manifest mechanism is introduced. M7.5.4 does not silently revise or replace an existing manifest.

The manifest establishes exactness relative to the recorded dependency-edge set. It does not prove that the caller identified every real-world dependency. That remains a provenance-authoring and independent-review obligation.

## 4. Deterministic transitive invalidation

`invalidate_dependency`:
1. acquires a SQLite write transaction;
2. builds the reverse adjacency from the immutable dependency edges;
3. traverses dependents breadth-first, ordering each adjacency set lexically;
4. appends one invalidation record for each transitive dependent;
5. returns the deterministic affected-node sequence.

Invalidation IDs are derived from the caller's stable root change ID and affected node ID. Repeating the same change ID and payload is idempotent. Reusing the same change ID with conflicting content is rejected by the event ledger's duplicate-record protection.

The root node is not marked stale by this operation. Unrelated dependency branches remain unaffected. Invalidation never deletes, overwrites or mutates the completeness claim or its earlier evidence.

A node that has already been invalidated cannot be reintroduced as a fresh dependency or have its dependency set extended. A newly assessed claim must use a new claim ID and new source/version references.

## 5. Freshness-gated negative-claim reuse

M7.5.3's original `evaluate_negative_claim` continues to check scope, predicate, subject, snapshot, completeness and closed-world rule preconditions.

New API:
`evaluate_negative_claim_with_freshness(claim, request, freshness)`

This wrapper additionally requires a matching `FreshnessResult` for `claim:<claim_id>` with status `FRESH`. Both `INVALIDATED` and `UNKNOWN` fail closed. A result for a different claim ID is rejected.

The API does not itself fetch or trust a change feed. Callers must obtain the result from the provenance store and must ensure relevant source changes are reported to `invalidate_dependency`. The original M7.5.3 evaluator remains available for isolated contract checking, but it is not sufficient by itself for operational reuse of a claim after M7.5.4.

## 6. Schema migration

The ledger migrates from the M7.5.3 three-record-type schema to the expanded provenance schema without discarding or rehashing prior rows. Existing sequence numbers, payload digests, previous hashes and event hashes are copied intact. A dedicated test constructs an M7.5.3-style ledger, opens it with the new store, verifies the original chain, appends a provenance edge and verifies the extended chain.

This is a local SQLite schema migration, not a distributed migration or backup/restore guarantee.

## 7. Validation scope

The M7.5.4 suite covers:
- cycle rejection before append;
- idempotent edge recording and conflicting stable-ID reuse;
- claim-to-snapshot/method/evidence dependency construction;
- exact dependency-manifest enforcement;
- freshness `UNKNOWN` when a manifest is absent or incomplete;
- freshness becoming `UNKNOWN` when a new edge appears after a manifest;
- deterministic transitive invalidation;
- preservation of unrelated sibling branches;
- idempotent invalidation and append-only history;
- rejection of stale dependency reuse;
- freshness-gated negative-claim evaluation;
- M7.5.3-to-M7.5.4 schema migration with hash-chain preservation.

The workflow reruns the M7.5.1, M7.5.2 and M7.5.3 suites as regression protection.

Exact-source validation record: [AE-32C-M7.5.4-Validation-Record-45898608483.md](AE-32C-M7.5.4-Validation-Record-45898608483.md). The validated source SHA is `3c2a1a2f76b9bf8520d3e7b3d245d8768b038ad0`; all 49 tests across M7.5.1–M7.5.4 passed.

## 8. Explicit limitations and non-goals

M7.5.4 does not:
- discover every dependency automatically;
- verify that a caller's dependency manifest is semantically exhaustive;
- authenticate source-change notifications or the identity of their producer;
- compare `expected_revision` against a trusted live source registry;
- detect a source change unless an upstream observer reports it;
- reverse an invalidation or automatically revalidate an old claim;
- prove evidence authenticity, correctness or independent verification;
- infer proposition truth or falsity;
- connect invalidation or freshness status to deterministic audit gates;
- establish production durability, backup/restore, or external tamper resistance.

The dependency graph is a provenance declaration and invalidation mechanism, not a complete software supply-chain attestation system. A signed/versioned source registry, independently verified change feed, and controlled claim re-issuance remain future work.

## 9. Architectural constraints

The implementation preserves the project-wide boundaries:
- Typed, explicit provenance relationships rather than implicit inference from missing graph records.
- Immutable evidence and append-only lifecycle history.
- A deterministic, bounded invalidation traversal.
- No LLM, solver or graph backend authority to mutate an audit decision.
- No modification to the frozen M7.4 baseline.

M7.4 remains `PARTIAL — FROZEN BASELINE`. M7.5.4 does not upgrade that status or confer production approval.

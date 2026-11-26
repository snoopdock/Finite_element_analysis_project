# AE-32C M7.5.6 — Recursive Provenance Freshness Closure

**Status:** Implemented and CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.4 provenance dependencies, freshness and invalidation; M7.5.5 assurance arguments and defeaters  
**Validated source revision:** `89624f59beb3274d07043f13530ca243d72233c1`  
**Validation run:** [45900529432](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45900529432)  
**Authority:** provenance closure reporting only; no proposition-truth inference or audit-gate authority

## 1. Problem statement

M7.5.4's `EpistemicStore.freshness_status(node_id)` verifies a node's own invalidation history and whether its dependency manifest exactly matches its recorded outgoing dependency edges. It does not recursively inspect the freshness of the nodes named by those edges.

Consequently, a composite node can receive local status `FRESH` even when one of its dependencies has no manifest and would independently receive `UNKNOWN`. This is a distinction between **local manifest integrity** and **transitive provenance closure**. The existing API remains useful for the former, but it must not be mistaken for the latter.

M7.5.6 adds an explicit recursive closure assessment without silently changing the established M7.5.4 local-status contract.

## 2. Objective

Provide a deterministic, fail-closed answer to:

> Is this node fresh, given not only its own declared dependency set, but also the recursively declared and non-invalidated state of every dependency reachable from it?

The closure operation must be bounded by the finite set of persisted dependency nodes, cycle-safe, deterministic, and evaluated against one SQLite read snapshot.

## 3. Terminal dependencies

A dependency leaf must not become fresh merely because it has no outgoing edges. Absence of edges is ambiguous: the node may be a genuine terminal source, or its dependencies may simply not have been declared.

M7.5.6 therefore introduces an **explicit empty dependency manifest** as a terminal-node declaration:

- no manifest: `UNKNOWN`;
- manifest with one or more exact edges: composite node;
- manifest with zero edges: explicitly declared terminal node.

This is a declaration, not independent authentication of the source. The identity, revision, observation method, and evidence supporting a terminal declaration remain caller-supplied and must be documented as such. M7.5.6 does not introduce signatures or a trusted source registry.

## 4. Required semantics

The new `freshness_closure(node_id)` operation evaluates a single consistent ledger snapshot.

For each visited node:

1. Any persisted invalidation makes that node `INVALIDATED`.
2. Missing manifest makes that node `UNKNOWN`.
3. A manifest whose edge IDs differ from the complete persisted outgoing edge set makes that node `UNKNOWN`.
4. An exact empty manifest establishes an explicitly declared terminal node.
5. For a composite node, recursively evaluate every dependency.
6. Any invalidated dependency makes the root closure `INVALIDATED`.
7. If no dependency is invalidated but at least one is unknown, the root closure is `UNKNOWN`.
8. The root closure is `FRESH` only if every reachable node is either an explicitly declared terminal or a composite node whose entire dependency closure is fresh.

The traversal must detect cycles defensively even though the write API rejects cycle-forming edges. A detected cycle yields `UNKNOWN` (not `FRESH`).

The returned result must preserve the requested root node ID, status, relevant invalidation IDs and a reason that distinguishes local failure from transitive failure.

## 5. Compatibility

- Preserve `freshness_status(node_id)` as the M7.5.4 local check.
- Add `freshness_closure(node_id)` as the stricter transitive operation.
- Permit an explicit empty `ProvenanceManifest.edge_ids` tuple.
- Existing non-empty manifests and historical event hashes must remain unchanged.
- No automatic migration or rewrite of existing manifests.
- M7.5.3 negative-claim evaluation remains unchanged; callers that require transitive freshness must pass the result of `freshness_closure` to `evaluate_negative_claim_with_freshness`.
- M7.5.5's caller-supplied freshness map remains available but is not upgraded to a store-backed guarantee by this milestone.

## 6. Structural and behavioral acceptance tests

The suite must verify at least:

- a terminal node without a manifest is `UNKNOWN`;
- an explicitly manifested empty terminal node is `FRESH`;
- a composite node with a fresh terminal dependency is `FRESH`;
- a composite node with an unmanifested dependency is `UNKNOWN`, even when its own local status is `FRESH`;
- a transitive invalidation makes the root closure `INVALIDATED`;
- an unknown dependency takes precedence over a local-only `FRESH` result;
- a manifest mismatch is `UNKNOWN`;
- a cycle introduced by controlled test-fixture tampering is not reported as fresh;
- multiple dependency branches produce deterministic results;
- concurrent writes cannot create a mixed-snapshot closure result;
- existing M7.5.1–M7.5.5 suites continue to pass;
- existing M7.5.4 event history and hash chain remain intact.

## 7. Explicit non-goals

M7.5.6 does not:

- authenticate terminal declarations or caller identity;
- independently verify source revisions or source-change notifications;
- discover undeclared dependencies;
- make separate SQLite ledgers transactionally atomic;
- authenticate evidence or prove evidence independence;
- infer proposition truth, probability or confidence;
- authorize ALLOW, DENY, acceptance, or any deterministic audit-gate transition;
- claim production durability, external anchoring, or administrator-resistant tamper proof.

## 8. Exit criterion

The M7.5.6 implementation and CI exit criterion are met for the exact Stage1 revision recorded above. The dedicated suite and all M7.5.1–M7.5.5 regression suites passed. The detailed evidence is recorded in [AE-32C-M7.5.6-Validation-Record-45900529432.md](AE-32C-M7.5.6-Validation-Record-45900529432.md).

## 9. Implementation and validation result

The implementation:

- permits an exact empty dependency manifest as an explicit terminal declaration;
- updates local `freshness_status` to recognize an exact empty manifest as fresh;
- adds `EpistemicStore.freshness_closure(node_id)`, an iterative depth-first traversal that avoids Python recursion-depth failure;
- reads dependencies, manifests and invalidations from one SQLite read snapshot after verifying the event hash chain;
- returns `INVALIDATED` if the root or any reachable dependency is invalidated;
- returns `UNKNOWN` if a reachable node lacks a manifest, has a manifest mismatch, or participates in a detected cycle;
- returns `FRESH` only when every reachable node has an exact manifest and every terminal is explicitly declared.

Validation on the exact revision:

- M7.5.1: 14 passed
- M7.5.2: 9 passed
- M7.5.3: 14 passed
- M7.5.4: 12 passed
- M7.5.5: 8 passed
- M7.5.6: 9 passed
- **Total: 66 passed**
- Python 3.11 compile: passed
- Workflow run: `45900529432`
- Artifact: `m7-5-epistemic-validation-45900529432-1`
- Artifact SHA-256: `5478734c9f4b63afd7a607832864e893f364edd24aca3bc2fb32fb8bd5ba8bdc`

Passing tests establish CI validation only. They do not authenticate terminal declarations, verify source-change notifications, or establish production approval.

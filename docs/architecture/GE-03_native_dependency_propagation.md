# GE-03 Revision 1 — Native Graph Dependency Propagation and Impact Review

**Milestone name:** GE-03 (the graph-engine detour). **CI compatibility profile:** `G4.3`. This does not rename or start the original G4 RDF Export milestone.

## Why the prior patch failed

The previous `main/.github/workflows/ge03_manual_impact_analysis.yml` checked out `main` and attempted to open `.graph-state/scientific/latest.json`. The 2026-10-13 snapshots show no such object. GE-02 persists `HEAD.json`, CAS commits in `commits/<digest>.json`, immutable GE-01 snapshots in `objects/<digest>.json`, and native deltas in `transitions/<digest>.json`. Only the development branch has the committed graph state. The former `tools/ge03_impact_analysis.py` also incorrectly identified *every node* as an impact candidate.

## Native pipeline

1. Manually dispatch from `main` with `branch=stage1/section-uuids`. GitHub checks out that branch in `source/` with no persisted credentials.
2. Run the focused GE-03 tests using `PYTHONPATH=source`.
3. Independently verify the entire GE-02 committed history using `PersistentDomainGraphStore.verify()` (CAS digests, reconstructed snapshots, transitions, generations, and HEAD).
4. Choose one read-only comparison:
   - `candidate`: validate an explicitly named scientific-knowledge JSON and project it through GE-01. Compare its projected view against verified GE-02 HEAD with the native `_transition` / `SemanticGraphEvolutionService` API. No publication occurs.
   - `latest-transition`: read the transition referenced by the most recent verified GE-02 commit. If the store is at generation 1, clearly report `no_prior_transition` and zero impacts.
5. Extract direct graph changes from the native `GraphDelta` and transitive review candidates from GE-02's bounded reverse traversal. A changed source concept should identify dependent concepts and propositions, but never automatically infer scientific truth.
6. Produce an exclusive, deterministic JSON report **outside the checked-out source**. GitHub uploads reports as temporary artifacts; it does not modify the development branch.

## Verified report fields

`store_head_sha256`, `store_generation`, baseline/current snapshot digests, `delta_id`, `direct_changes`, review nodes and graph distances, `report_sha256`. The hash is SHA-256 over canonical JSON *without* the hash field; it is an integrity check, not cryptographic attestation.

Flags `scientific_truth_established`, `automatic_approval_permitted`, and `authoritative_graph_mutation_permitted` always remain `false`. `document_section_mapping_available` remains `false` unless a later integration provides an explicit, verified relation connecting graph nodes to document sections. **Do not interpret impacted graph nodes as verified impacted LaTeX sections.**

## Failure and resource semantics

Missing/empty/corrupt state, symlink graph objects, corrupt transitions, unsafe input traversal, malformed graph identities, duplicate JSON keys, unsafe report paths, and nonexistent baselines fail closed. The GE-02 bounded candidate traversal limit is preserved. No arbitrary graph should be accepted as a fabricated GE-02 snapshot.

## Manual GitHub runs

**Validation**: Actions → `Manual Validation Dispatcher` → target `stage1/section-uuids`, profile `G4.3`, regression mode `profile`. This runs focused and full repository suites with existing evidence publication.

**Functional example**: Actions → `GE-03 Manual Native Graph Impact Review` → branch `stage1/section-uuids`, mode `candidate`, path `examples/graph_engine/ge03_demo_changed_graph.json`. It should report exactly three impact candidates with dependency distances `0`, `1`, `2` from the already-persisted demonstration HEAD. Running `latest-transition` while HEAD is generation 1 correctly reports no prior change; it does not invent one.

This is a review-only graph-engine capability, not an autonomous reviewer, SAT proof, or FEM scientific correctness certificate.

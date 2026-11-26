# Graphify Branch Backend Status Assessment — 2026-11-26

## 1. Purpose and evidence boundary

This record uses the independently generated Graphify snapshots to locate and assess graph-backend implementation paths on each branch. It does not compare branch history, rank libraries, or infer suitability from graph size.

Graphify is code-structure evidence only. The status decisions below combine:
- the exact branch-pinned Graphify snapshots;
- source-tree and call-path inspection;
- the existing E.8.5 native conformance and E.8.8 repository-backed reports;
- the detached G7 artifact dossier for the cited test run.

A dependency, import, adapter class, or graph edge alone is not execution proof.

## 2. Snapshot identity

| Branch | Analyzed source SHA | Graphify | Nodes | Edges | Communities | Graph JSON SHA-256 |
|---|---|---:|---:|---:|---:|---|
| main | `b1199ee3bf2f4cbbc5b99f13f43f9230996d10aa` | 0.9.112 | 5,964 | 10,042 | 439 | `eefe018ddc7302399093ee002bf99c64e52e44f9179e32ad8d2df18991de59f1` |
| stage1/section-uuids | `2efb8b44e69a0f3a4512f8164668c41af4127d75` | 0.9.112 | 18,720 | 47,744 | 1,034 | `f458d649222ba8bf2a125e89d03b0efbc67e648b0dd9f9aef6e2c69c7d72e0b2` |

The Graphify workflow completed successfully in run [45770252227](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45770252227). The source and graph snapshot pipeline completed successfully in run [45770251815](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45770251815). The Stage1 source tip at analysis time was `2efb8b44e69a0f3a4512f8164668c41af4127d75`. This assessment was subsequently committed as a documentation-only change, commit `6c90c40244494fa31272f87e0288a3a3a44aea5a`; that commit changes only this report and does not change the analyzed application or backend code.

Artifacts are stored under:
- `branch-graphify-results/latest/main/`
- `branch-graphify-results/latest/stage1-section-uuids/`

Each directory contains `graph.json`, `graph.html`, `GRAPH_REPORT.md`, `analysis-report.md`, `run-metadata.json`, and `graphify-run.log`.

## 3. main — bounded backend status

**Analyzed source:** `b1199ee3bf2f4cbbc5b99f13f43f9230996d10aa`

The main source tree contains the canonical semantic graph and graph-analysis/service modules, but it does not contain `audit_engine/semantic_audit/graph/backend/`. In particular, it has no `BackendFactory`, no five adapter implementations, and no native adapter traversal implementation.

The graph analysis engine contains conditional dispatch references for:
- `audit_engine.semantic_audit.graph.backend.networkx_traversal.NetworkXGraphTraversalEngine`;
- `audit_engine.semantic_audit.graph.backend.adapter_traversal.NativeAdapterGraphTraversalEngine`.

Those referenced modules are absent from this source snapshot. Consequently, selecting one of the five optional native traversal backends cannot reach an adapter implementation on this branch. The reference traversal remains the implemented path.

| Backend | main status | Scope and basis |
|---|---|---|
| NetworkX | **DORMANT** | Native traversal adapter module absent; conditional import target is unreachable |
| SciPy | **DORMANT** | Native adapter traversal module and SciPy adapter absent |
| python-igraph | **DORMANT** | Native adapter traversal module and igraph adapter absent |
| graph-tool | **DORMANT** | Native adapter traversal module and graph-tool adapter absent |
| SNAP | **DORMANT** | Native adapter traversal module, SNAP adapter, and worker adapter absent |

This is a bounded statement about the five native traversal adapters, not a claim that the entire graph-analysis subsystem is dormant. The reference Python traversal and canonical graph remain present.

## 4. stage1/section-uuids — implementation and native evidence

**Analyzed source:** `2efb8b44e69a0f3a4512f8164668c41af4127d75`

The branch contains the complete five-backend adapter layer:
- `BackendFactory` maps `networkx`, `scipy`, `igraph`, `graph-tool`, and `snap` to concrete adapter implementations;
- `GraphAnalysisEngine` dispatches NetworkX to its dedicated traversal engine and the other four backends to `NativeAdapterGraphTraversalEngine`;
- `SemanticGraphAnalysisService` passes the trusted traversal-backend selection into the analysis engine;
- adapters expose backend-specific native local-adjacency operations and occurrence-preserving records.

### 4.1 Native mechanisms

| Backend | Native query mechanism evidenced |
|---|---|
| NetworkX | Directed `MultiDiGraph` successor/predecessor adjacency with keyed edge occurrences |
| SciPy | CSR outgoing-row and CSC incoming-column access, with exact semantic edge-occurrence side channels |
| python-igraph | Native incident edge IDs for incoming/outgoing adjacency |
| graph-tool | Native per-vertex `out_edges()` / `in_edges()` iterators and edge-index mapping |
| SNAP | `TNEANet` edge-ID queries through an isolated CPython 3.9 worker |

### 4.2 Native conformance and repository-backed execution

The latest detached-verified five-backend E.8.5/E.8.8 evidence is run [45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671), source SHA `0b37e79c9942e483cea770fc96138c4f185753e1`. Its detached dossier is [45602963647](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647).

For every backend, the dossier records:
- E.8.5: seven cases, 14/14 parity-verified queries, zero query failures and zero parity failures;
- E.8.8: 43/43 parity-verified repository-backed queries, zero query failures and zero parity failures;
- E.8.8 context parity: 7/7 `trace_execution_context`, 16/16 `find_workflow_context`, and 16/16 nested workflow-context operations;
- native adjacency telemetry: 34 lookups / 96 edge occurrences read for E.8.5, and 45 lookups / 86 edge occurrences read for E.8.8.

Recorded native environments:
- NetworkX 3.6.1;
- SciPy 1.17.1;
- python-igraph 1.0.0;
- graph-tool 3.9;
- SNAP 6.0.0 in the isolated worker.

The E.8.5/E.8.8 artifacts were bound to run ID, attempt, branch, source revision, artifact ID, archive size and SHA-256, then independently checked by the detached verifier. The dossier explicitly limits this to artifact integrity and report consistency; it is not signed runner attestation or a historical rerun.

### 4.3 Applicability to the current Stage1 snapshot

The Graphify snapshot is 93 commits after the E.8.5/E.8.8 tested SHA. GitHub's commit comparison from `0b37e79c9942e483cea770fc96138c4f185753e1` to `2efb8b44e69a0f3a4512f8164668c41af4127d75` reports no changes to:
- the graph backend adapter modules;
- the graph analysis engine or graph service;
- E.8.3/E.8.5 adapter conformance tests;
- the E.8.5/E.8.8 native and repository conformance runners;
- the repository evidence-tool implementation.

The intervening commits add or update AE-32C publication, snapshot, workflow-controller, and evidence documentation. Therefore the native conformance evidence remains applicable to the unchanged backend implementation and test paths, but the historical run must still be identified by its original source SHA. It must not be relabelled as a fresh exact-`2efb8b44` test run.

| Backend | stage1 status | Supported operation scope |
|---|---|---|
| NetworkX | **FUNCTIONAL** | E.8.5 deterministic semantic traversal and E.8.8 tested repository context operations |
| SciPy | **FUNCTIONAL** | E.8.5 deterministic semantic traversal and E.8.8 tested repository context operations, using hybrid CSR/CSC plus semantic side channels |
| python-igraph | **FUNCTIONAL** | E.8.5 deterministic semantic traversal and E.8.8 tested repository context operations |
| graph-tool | **FUNCTIONAL** | E.8.5 deterministic semantic traversal and E.8.8 tested repository context operations in the recorded conda-forge environment |
| SNAP | **FUNCTIONAL** | E.8.5 deterministic semantic traversal and E.8.8 tested repository context operations through the restricted isolated worker only |

These are operation-scoped implementation statuses. They do not mean that each backend is suitable for every audit-engine task or deployment environment.

## 5. Important limitations and unresolved decisions

1. **Task suitability is not accepted.** The M7.4 contract and preliminary matrix continue to classify all 20 task/backend pairs as **Insufficient evidence**. The native traversal and repository-context passes do not close every task-specific semantic, workload, mutation-safety, operational, and domain gate.
2. **G4 remains Partial.** The detached dossier records a Windows handle-bound junction-replacement test pass, but repository-wide atomic snapshot semantics and other filesystem race/aliasing cases remain unresolved.
3. **SNAP is environment-constrained.** Its native execution is through a restricted CPython 3.9 / SNAP 6.0 worker, orchestrated from Python 3.11. It is not an in-process Python 3.11 adapter.
4. **SciPy is a hybrid representation.** CSR/CSC stores topology and multiplicity; exact relation, attributes, metadata and provenance are reconstructed from semantic side channels. The sparse matrix alone is not a lossless semantic multigraph.
5. **Full projection audits occur at query boundaries.** The current non-NetworkX traversal engine performs complete native node/edge read-back validation at construction and after each bounded query. The NetworkX traversal path also performs full projection verification around query/context operations. This is an integrity measure, but it means a query includes an O(V+E) validation pass in addition to reached-node native adjacency. It should remain explicit in operational qualification; whether to retain this boundary check or move it to an explicit audit/cache-invalidation protocol is a separate architecture decision. It does not negate the observed native adjacency calls.
6. **No library ranking or automatic selection.** The backends are computational options. Their use must be selected according to the required operation and its evidence, not a universal performance score.

## 6. Current conclusions

- The redesigned Graphify workflow is operational and publishes independent, commit-pinned branch snapshots.
- On `main`, the five optional native adapter paths are dormant/unavailable in the bounded source scope; reference traversal remains available.
- On `stage1/section-uuids`, all five adapters have native E.8.5 and repository-backed E.8.8 execution evidence for the stated operations.
- All 20 formal task/backend suitability outcomes remain **Insufficient evidence**.
- No automatic backend selection, production promotion, scientific approval, or production approval is authorized. `production_approval=false` remains in force.

## 7. Primary evidence links

- [Graphify workflow run 45770252227](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45770252227)
- [AE-32C source/graph snapshot workflow run 45770251815](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45770251815)
- [Stage1 native conformance run 45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671)
- [Detached artifact verifier run 45602963647](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647)
- [M7.4 task-suitability contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md)
- [M7.4 preliminary task/backend evidence matrix](AE-32C-M7.4-Preliminary-Task-Backend-Evidence-Matrix.md)
- [Graphify branch backend evidence protocol](Graphify-Branch-Backend-Evidence-Protocol.md)

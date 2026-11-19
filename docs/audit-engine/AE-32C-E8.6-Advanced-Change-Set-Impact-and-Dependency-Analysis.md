# AE-32C E.8.6 — Advanced Change-Set Impact and Dependency Analysis

**Release:** AE-32C E.8.6  
**Branch:** `stage1/section-uuids`  
**Parent:** E.8.5, G9.42 run `44591162575`, commit `f228173b3e604dd08db5e24bc76e130ab8245b56`

## 1. Objective

E.8.6 extends the E.8.4 single-entity impact capability into bounded change-set analysis. A caller can submit multiple changed files, modules, or symbols in one graph query and receive a deterministic union of affected candidates, per-source attribution, overlap information, dependency-cycle observations, and explicit structural risk indicators.

The implementation continues to use the canonical `SemanticGraph` and the configured traversal backend. NetworkX and SciPy therefore participate through the same backend/query path as E.8.5. The pure-Python reference traversal remains the parity oracle.

## 2. Multi-source change sets

`QueryType.IMPACT` now accepts 1–25 unique source entities. Query validation rejects duplicate IDs and sets larger than 25. The LLM-facing `graph_neighbors` tool retains the required `node` argument and accepts up to 24 additional `changed_nodes` when `direction="impact"`.

The analyzer sorts source IDs before execution so the result does not depend on caller ordering. It divides the configured global traversal budgets across the sources:
- `max_visited_nodes`: at most 2,000 total across source analyses
- `max_traversal_steps`: at most 10,000 total across source analyses
- `max_depth`: existing bounded impact depth, 1–5

Each source is analyzed with the existing ownership-resolution and reverse-dependency semantics. Results are merged by candidate node ID. The merged candidate records:
- `affected_by`: sorted changed-source IDs
- `affected_by_count`
- `shared_change_impact`
- per-source impact depth and total path length
- per-source evidence paths
- unioned relationship types and evidence IDs

The aggregate reports unique candidate count, shared-impact count, per-source candidate counts, direct/transitive counts, and traversal truncation state.

## 3. Dependency-cycle analysis

After the impact frontier is assembled, E.8.6 checks the induced impacted subgraph for strongly connected components over `IMPORTS` and `DEPENDS_ON` edges only. It uses iterative Kosaraju traversal, avoiding Python recursion-depth dependence.

A component is reported as a dependency cycle when it contains more than one node or a self-loop. Reports include:
- deterministic cycle ID
- sorted node IDs
- relation types
- edge-occurrence count
- exact evidence IDs
- self-loop flag

The cycle scan is bounded to 2,000 impacted nodes and 50,000 graph edge occurrences. If either bound prevents a complete scan, `cycle_analysis_status` reports an incomplete state. An incomplete scan is never described as proof that no cycle exists.

This is structural analysis only. It does not establish that a cycle is harmful, reachable at runtime, or a defect.

## 4. Structural risk indicators

E.8.6 reports evidence-bound indicators rather than a numeric risk score:
- `dependency_cycle_observed`
- `shared_impact_overlap`
- `impact_frontier_incomplete`
- `dependency_cycle_scan_incomplete`

Every indicator explicitly states that severity has not been assessed. The engine does not infer missing test coverage from absence of a `TESTS` edge, and does not infer runtime execution from static relationships.

## 5. Candidate classification

Impact candidates are classified where the canonical node type or source path supports it:
- tests
- workflows
- symbols
- modules
- files
- other

The evidence tool exposes `impacted_tests`, `impacted_workflows`, and `impacted_symbols` as candidate groupings. These are observed graph relationships, not proof that tests execute or workflows are active.

## 6. Evidence and determinism

All graph observations remain linked to `EvidenceRecord` IDs derived from canonical edge fingerprints. Cycle reports add evidence records for the exact dependency edge occurrences used to establish strongly connected components.

The result is deterministic for a fixed graph snapshot, source set, constraints, and query ID. Source order is normalized. Candidate paths and evidence IDs are sorted. Backend parity remains checked by the existing traversal engine.

## 7. Safety and authority boundary

E.8.6 is read-only:
- no repository files are modified
- no shell commands are executed
- no provider calls are made by graph analysis
- no action plan is approved or executed
- no severity or semantic correctness is asserted
- no automatic approval or authoritative graph mutation is permitted

The LLM can request impact analysis and interpret the returned evidence, but it does not gain additional execution authority.

## 8. Validation

The G9.42 profile now includes `tests/semantic_graph/test_e86_change_set_impact.py`. The new tests cover multi-source aggregation, order independence, shared impact attribution, dependency SCCs and self-loops, evidence preservation, traversal/cycle bounds, duplicate and overlarge source rejection, tool schema compatibility, and NetworkX/SciPy parity.

Local focused and profile results are recorded in the package `TEST_RESULTS.md`. GitHub G9.42 full-regression validation is required after upload.

## 9. Known limitations

- Native E.8.5 conformance evidence for igraph, graph-tool, and SNAP remains outstanding; the accepted G9.42 run skipped their native tests.
- Cycle analysis is restricted to the impacted node set and `IMPORTS`/`DEPENDS_ON`; it does not enumerate every simple cycle.
- Static impact candidates can be false positives or incomplete when the source graph is incomplete or a declared bound is reached.
- No live LLM investigation is included in this release.

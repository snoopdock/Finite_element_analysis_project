# AE-32C M2 — Context and Workflow Tool Backend Routing

**Status:** Initial implementation committed; exact-commit validation pending  
**Target branch:** `stage1/section-uuids`  
**M1 prerequisite:** NetworkX acceptance recorded in [M1 NetworkX Validation Record](AE-32C-M1-NetworkX-Validation-Record.md)  
**Implementation snapshot:** `7e9a680e41dfb4fd322aeba29ddd18e10b3b490f`

---

## 1. M2 objective

M2 completes the repository context tools' integration with the selected graph computation backend. The two affected tools are:

- `trace_execution_context`
- `find_workflow_context`

They retain their domain-specific traversal and result semantics. Only their local adjacency acquisition is moved behind the backend-independent `GraphQuery` / `SemanticGraphAnalysisService` boundary.

## 2. Implementation changes

### 2.1 Backend-independent one-hop adjacency

In `audit_engine/semantic_audit/ae32b/evidence_tools.py`, `_context_edges` now creates a one-hop `GraphQuery` of type `DEPENDENCY` with explicit direction, relation filters and bounded traversal constraints. It submits the query through `self.graph_service.analyze()`.

The method converts returned evidence records back into canonical `SemanticEdge` values using their source/target/relation fields and edge-attribute/edge-metadata provenance. The context tools continue to perform their own BFS, type-checking-only import exclusion, path ordering, source-line attribution, entrypoint derivation, workflow scoping and result truncation.

### 2.2 Removal of silent canonical-edge fallback

The former implementation called a NetworkX-specific `context_edges` hook when present, but otherwise scanned `self.graph.edges` and counted a context backend bypass. M2 removes that branch. Context adjacency is now requested through the same graph-query service used by the other graph tools; unsupported or incomplete query results fail explicitly rather than silently falling back to a canonical full-edge scan.

A truncated one-hop adjacency response raises `context_adjacency_incomplete`. The context tools do not present a partial adjacency set as complete.

### 2.3 Operation-level telemetry

The evidence-tools boundary now records per-operation:

- adjacency queries attempted, succeeded and failed;
- native adjacency lookups;
- native edge occurrences read;
- parity-verified queries and parity failures.

The counters are exposed through `graph_runtime_report()` under `context_operation_telemetry`. The legacy bypass count remains visible and should stay at zero.

### 2.4 Regression guard

A new test in `tests/semantic_graph/test_e88_networkx_repository_backend.py` replaces the old NetworkX-specific context hook with a function that raises. It then invokes both context tools and asserts successful results, zero bypasses, native adjacency telemetry and per-query parity verification. This makes the backend-neutral routing requirement executable rather than documentary.

## 3. Commits

| Commit | Change |
|---|---|
| `7d9e8f1aac3b873e689a45f525060c60420314bc` | Route context adjacency through `GraphQuery` and the graph analysis service |
| `7e9a680e41dfb4fd322aeba29ddd18e10b3b490f` | Add regression assertion that context tools do not call the backend-specific hook |

The implementation was committed directly to `stage1/section-uuids`. No changes were made to `main`.

## 4. Validation boundary

No tests or workflows have been run for the M2 commits. The prior G9.42 result validates source commit `fb3f26e...` only; it must not be carried forward as validation of these M2 changes.

M2 remains open until an exact-commit validation confirms:

1. existing context-tool semantic tests pass;
2. the new backend-neutral routing test passes;
3. the E.8.8 repository conformance runner reports zero bypasses and successful native adjacency/parity telemetry for both context tools;
4. source-line provenance, type-checking-only exclusions, workflow relationship types, active-workflow scope and bounded/truncated behavior remain unchanged;
5. full regression passes or any failures/skips are explicitly adjudicated.

## 5. Remaining M2 work

- Review and test domain-specific semantic parity for execution-context and workflow-context outputs.
- Verify nested `trace_execution_context.workflow_context` telemetry and direct `find_workflow_context` telemetry independently.
- Verify failure behavior for an unavailable/unaccepted backend and for incomplete local adjacency.
- Run the exact-commit G9.42 validation after the implementation snapshot is ready.
- Update this record and the roadmap with the run ID, source SHA, artifact digests and result.

M2 does not implement SciPy CSR/CSC adjacency and does not accept non-NetworkX backends. Those remain separate roadmap milestones.

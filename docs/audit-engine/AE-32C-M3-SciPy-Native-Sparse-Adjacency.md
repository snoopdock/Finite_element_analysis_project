# AE-32C M3 — SciPy Native Sparse Adjacency Implementation Record

**Status:** Accepted for the tested SciPy CSR/CSC native-adjacency and repository context-tool path by G9.42 run 44898320570  
**Milestone:** M3 — SciPy native sparse adjacency  
**Predecessor:** M2 validated by G9.42 run [44894696688](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44894696688) against source SHA `9dd02f7f98e0ad25d2225c638ed14bad4bd5d4e6`  
**Scope:** SciPy only. This acceptance does not promote igraph, graph-tool or SNAP.

---

## 1. Objective

Replace the non-NetworkX full-graph adjacency reconstruction for SciPy with native sparse local adjacency access while preserving the canonical semantic graph as the authority for edge identity and evidence.

The SciPy projection is hybrid:

- CSR stores directed connectivity and parallel-edge multiplicity.
- CSC provides a column-oriented index for incoming adjacency.
- Side channels retain exact edge occurrence IDs, relation labels, attributes and metadata.

The sparse matrix is not treated as a lossless semantic edge store.

## 2. Implementation

### 2.1 Projection construction

`SciPyAdapter` now builds:

- the existing CSR matrix for outgoing adjacency;
- a CSC matrix derived once from CSR for incoming adjacency;
- the existing pair-to-occurrence mapping and semantic payload side channels.

The full projection iterator validates the CSR and CSC shapes and confirms that CSC is an exact sparse transpose-index representation of the CSR connectivity/multiplicity values. It also checks each CSR coordinate against its occurrence side channel.

### 2.2 Query-time adjacency

`iter_adjacent_edge_occurrences(node_id, direction)` is the native query operation:

- `OUTGOING`: reads one CSR row using `indptr`, `indices` and `data`;
- `INCOMING`: reads one CSC column using its corresponding sparse index arrays;
- `BOTH`: unions the two local results by canonical occurrence ID.

Every sparse coordinate is expanded to the exact occurrence list in the side channel. The adapter checks multiplicity and source/target/relation/occurrence identity before constructing typed `NativeEdgeOccurrence` records. Parallel edges with identical endpoints and relation labels remain distinct. A self-loop is returned once for `BOTH`.

No query-time call to `iter_native_edges()` or `iter_native_nodes()` is required.

### 2.3 Traversal integration

`NativeAdapterGraphTraversalEngine` retains the complete projection audit during construction. After that audit succeeds, SciPy queries receive empty Python adjacency indexes and override candidate selection to use `iter_adjacent_edge_occurrences`.

The existing deterministic BFS still owns:

- queue ordering and depth semantics;
- relation filtering;
- visited-node and step bounds;
- canonical evidence construction;
- result ordering and truncation reporting.

Per-query reference parity remains enabled by default.

Other non-NetworkX adapters retain their existing implementation; this milestone does not silently alter their acceptance state.

### 2.4 Observability

The SciPy adapter reports:

- native adjacency calls;
- CSR row lookups;
- CSC column lookups;
- sparse pair entries read;
- semantic edge occurrences returned.

The traversal engine separately reports native adjacency calls and occurrence reads. Projection node and edge-occurrence counts are cached from the one-time construction audit. SciPy runtime reporting therefore does not perform a hidden full-graph enumeration.

The registry now describes SciPy native adjacency as `implemented_unvalidated`. It does not mark the backend conformant or production-approved.

## 3. Added conformance coverage

The E.8.3 multi-backend test module now includes tests for:

1. outgoing CSR row access preserving both parallel A→B edge occurrences;
2. incoming CSC column access preserving exact incoming occurrence identity;
3. parity with the reference traversal;
4. full native node/edge enumeration being forbidden after construction during both queries and runtime reporting;
5. `BOTH` returning an incoming edge and a self-loop exactly once;
6. bounded depth-one traversal accessing only the reached start node's adjacency;
7. repository-backed SciPy conformance, including graph-to-source follow-through and context-tool telemetry.

These tests have been committed but **have not been executed locally or through a workflow by the implementer**. The user-run G9.42 workflow is the acceptance gate.

## 4. First G9.42 validation and corrective review

The first user-run G9.42 validation, [run 44895368283](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44895368283), checked out source SHA `78ece9ccdab4b4597930ba315d4c019175089119` and failed. The targeted suite reported 674 passed, 6 skipped and 2 failed; full regression reported 3,604 passed, 14 skipped and 3 failed. The three failures were:

1. Reference/native parity mismatch for `direction="both"` with a self-loop, caused by raw-string versus enum identity handling in the reference traversal.
2. SciPy repository context telemetry reporting zero native lookups because native-adapter result metadata omitted the per-query `backend_native_query_metrics` contract consumed by `RepositoryEvidenceTools._context_edges()`.
3. A stale M1 test expecting SciPy to remain `not_implemented`.

The review also found hard-coded NetworkX execution-mode labels in the repository conformance report. These would have misrepresented SciPy context execution even after the telemetry assertion was corrected.

The failure analysis and corrective commits are recorded in [M3 G9.42 Validation Failure Review](AE-32C-M3-Validation-Failure-44895368283.md). Corrections normalize traversal direction at the reference API boundary, expose per-walk SciPy native adjacency metrics, report the actual selected backend mode, and update/add regression assertions. These corrections have been committed but **have not yet been executed by a workflow**.

## 5. Second G9.42 validation and correction

The next user-run validation, [run 44896382956](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44896382956), tested Stage1 source SHA `60192a96dafef2e8f1381719950578d061114c2f`. It reported 676 passed, 6 skipped and 1 failed in the targeted suite; full regression reported 3,607 passed, 14 skipped and 1 failed. The sole failure was a stale NetworkX context-mode string in `test_e88_networkx_repository_backend.py`: the test expected `networkx_native_successor_predecessor_adjacency`, while the backend runtime and direct adapter test correctly report `networkx_successor_predecessor_adjacency`.

The assertion was corrected without changing production code. The failure analysis is recorded in [G9.42 Validation Failure Review — run 44896382956](AE-32C-G9.42-Validation-Failure-44896382956.md). The correction is committed as `4dc1a40681dab18b55f4fc4af0d45adbd21c8c83`; the documentation update follows in the same Stage1 branch. The SciPy-specific assertions passed in that run, but the overall validation failed and the provenance catalog was correctly blocked. Therefore M3 remains unvalidated.

## 5. Final G9.42 acceptance

G9.42 run [44898320570](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44898320570) validated the exact Stage1 source SHA `c40a258f627a1678036521e2474fccdd5537e46a` (Python 3.11.18; profile G9.42). The dispatcher itself ran from `main`, but the artifact identifies `stage1/section-uuids` and the exact target SHA above.

| Evidence | Result |
|---|---:|
| Validation-engine unit tests | 53 passed |
| Targeted suite | 683 total: 677 passed, 6 skipped |
| Full regression | 3,622 total: 3,608 passed, 14 skipped |
| Failures / errors | 0 / 0 |
| Evidence digest and checksum verification | Passed |
| Immutable evidence bundle | Published |
| Provenance catalog | Built and independently verified |

Validation report SHA-256: `250b8e5442f8dc15c0ade6c44a6ea51eb7032e0344934919b1a2d77616e5d0d1`.

Immutable bundle SHA-256: `b3b54793a40bb5ca13309ee103ee814c5410ff83dd838aef98458f5c88946bb5`.

The catalog entry records status and regression status as `passed`, with 683 targeted tests, and binds the report/bundle to the exact Stage1 source SHA. The 6 targeted and 14 regression skips remain explicit environmental exclusions; they do not negate the executed SciPy tests. This closes M3 for the tested SciPy implementation and repository context-tool path only. It does not establish a universal performance advantage or approve other optional backends.

## 6. Acceptance boundary

M3 is accepted for the tested path. The following broader claims are not established by this validation:

- actual installed SciPy version/API behavior in the G9.42 environment;
- all newly added sparse-adjacency tests passing;
- full regression compatibility;
- repository context-tool routing and source follow-through under SciPy;
- evidence digest and provenance catalog verification.

A successful synthetic or mocked test alone would not establish native SciPy acceptance. The workflow must run with the real SciPy dependency installed and the report must identify the exact Stage1 source SHA.

## 7. Files changed

- `audit_engine/semantic_audit/graph/backend/scipy_adapter.py`
- `audit_engine/semantic_audit/graph/backend/adapter_traversal.py`
- `audit_engine/semantic_audit/graph/analysis/traversal.py`
- `audit_engine/semantic_audit/graph/backend/capability_registry.py`
- `tools/gb04_repository_backend_conformance.py`
- `tests/semantic_graph/test_e83_multi_backend_traversal.py`
- `tests/semantic_graph/test_m1_adapter_protocol_networkx.py`
- `docs/audit-engine/AE-32C-M3-Validation-Failure-44895368283.md`
- `docs/audit-engine/AE-32C-Graph-Backend-Compatibility-and-Utilization-Roadmap.md`

## 8. Validation protocol

Run the existing manual validation dispatcher against:

- Branch: `stage1/section-uuids`
- Profile: `G9.42`

Acceptance requires the targeted suite and full regression to pass, the evidence integrity check to pass, and the provenance catalog to be built and independently verified. Report skips explicitly. Do not extend this acceptance to untested backends or workloads without separate evidence.


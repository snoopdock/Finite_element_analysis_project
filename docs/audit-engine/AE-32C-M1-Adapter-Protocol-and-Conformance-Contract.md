# AE-32C M1 — Native Graph Adapter Protocol and Conformance Contract

**Status:** M1 accepted for the NetworkX adapter contract on the validated Stage1 snapshot; other backend adapters remain unaccepted  
**Target branch:** `stage1/section-uuids` only  
**Depends on:** AE-32C Graph Backend Compatibility and Utilization Roadmap; M0 source baseline  
**Primary objective:** define one verifiable contract for native graph projection and per-node native adjacency before changing adapter implementations.

---

## 1. Purpose

### 1.1 Implementation record (2026-11-21)

The first implementation slice is committed on `stage1/section-uuids`:

- `SemanticGraphAdapter` now declares typed `NativeNodeRecord` and
  `NativeEdgeOccurrence` records, explicit full-projection inspection methods,
  and `iter_adjacent_edge_occurrences(node_id, direction)`.
- Unimplemented adapter adjacency fails explicitly with
  `NativeAdjacencyNotSupportedError`; the base contract does not silently scan
  the saved Python projection.
- `NetworkXAdapter` implements occurrence-preserving local adjacency through
  `MultiDiGraph.succ` and `pred`. `NetworkXGraphTraversalEngine` now invokes
  that typed adapter operation rather than duplicating direct native access,
  preserving parallel edges and returning a self-loop once for `BOTH`.
- The Python reference and NetworkX traversal paths now use the same
  one-occurrence self-loop rule for `BOTH`.
- A focused NetworkX protocol test module asserts explicit occurrence IDs,
  direction semantics, unknown/isolated-node behavior, payload isolation,
  independent self-loop expectations, observational runtime reporting, and proof that the traversal engine invokes the typed adapter method.

The implementation was validated on the exact Stage1 source commit by the
G9.42 Manual Validation Dispatcher run 44892453883. The full regression suite
includes all 18 tests in `test_m1_adapter_protocol_networkx.py`; the targeted
profile also executed the E.8.5 and E.8.8 test modules, including the
repository-conformance runner assertions. The validation record is
[AE-32C M1 NetworkX Validation Record](AE-32C-M1-NetworkX-Validation-Record.md).
This acceptance is scoped to the NetworkX protocol and repository path; it does
not accept SciPy, igraph, graph-tool or SNAP.


The current adapter interface describes projection export, capabilities, identity mapping and loss reporting. The traversal path additionally expects native node/edge iteration, while true native query execution requires a per-node adjacency operation. These runtime expectations are not yet expressed as one typed and testable contract.

M1 closes that gap. It must not merely rename existing full-graph readback methods. The contract must distinguish:

1. **Projection inspection:** complete native graph readback used to validate a projection.
2. **Query execution:** retrieval of the exact incident edge occurrences of a reached node through the selected library's native adjacency representation.
3. **Semantic result construction:** deterministic AE-32 logic over canonical edge occurrences.
4. **Acceptance evidence:** independently measured evidence that the actual native API and intended execution path were used.

M1 is a specification and test-first milestone. Backend-specific implementations follow only after the contract tests and the semantic decisions below are reviewed.

## 2. Authority model

The authority order is:

1. The immutable repository snapshot is the source evidence boundary.
2. The canonical `SemanticGraph` owns semantic node identities and edge-occurrence meaning for one graph snapshot.
3. A native library graph is a computational projection.
4. The adapter maps native objects and adjacency results back to canonical identities.
5. The AE-32 traversal/query service owns deterministic ordering, bounds, evidence records and result semantics.
6. The Python reference traversal remains a differential oracle, but not the only specification oracle.

A native backend must not become the authority for semantic identity, provenance, repository source content or query policy. It must not silently change query semantics or bypass the evidence/source-read boundary.

## 3. Proposed typed contract

The following is the proposed conceptual API. Exact class names and compatibility strategy can be settled during implementation, but the operations and semantics are required.

### 3.1 Native node record

A native node record must expose:

| Field | Meaning |
|---|---|
| `node_id` | Canonical semantic node identifier |
| `entity_type` | Canonical semantic entity type |
| `attributes` | Complete canonical node attributes |
| `metadata` | Complete canonical node metadata |

A backend's integer vertex index or library-specific node object must never be substituted for `node_id`. The backend identity mapping may retain its native identifier separately.

### 3.2 Native edge-occurrence record

Each edge record must represent one exact canonical edge occurrence, not one unique endpoint pair.

| Field | Meaning |
|---|---|
| `occurrence_id` | Unique edge-occurrence identity within the canonical graph snapshot |
| `source_id` | Canonical source node ID |
| `target_id` | Canonical target node ID |
| `relation_type` | Canonical relation label |
| `attributes` | Complete canonical edge attributes |
| `metadata` | Complete canonical edge metadata |
| `backend_edge_ref` | Optional opaque native edge identity for diagnostics/mapping |

The occurrence identity is currently represented by an index into the canonical edge sequence. Unless the graph model is separately extended with durable edge IDs, it must be treated as **snapshot-scoped**. A stable identity across graph rebuilds or graph versions is not implied by this integer alone. Runtime evidence should pair it with the canonical graph fingerprint.

Parallel edges with the same source, target and relation must still have different `occurrence_id` values.

### 3.3 Required operations

The contract should expose three distinct operations:

```python
iter_native_nodes() -> Iterable[NativeNodeRecord]

iter_native_edge_occurrences() -> Iterable[NativeEdgeOccurrence]

iter_adjacent_edge_occurrences(
    node_id: str,
    direction: TraversalDirection,
) -> Iterable[NativeEdgeOccurrence]
```

The first two operations support explicit full-projection validation. The third is the query-time operation. The implemented method names are `iter_native_nodes()`, `iter_native_edge_occurrences()`, and `iter_adjacent_edge_occurrences(node_id, direction)`. It must be implemented using the selected library's native indexed adjacency or incident-edge API.

The per-node method must:

- return exact edge occurrences, including parallel occurrences;
- preserve source, target, relation, attributes and metadata;
- respect outgoing, incoming and bidirectional direction;
- avoid scanning all native nodes or all native edges;
- avoid rebuilding global Python adjacency dictionaries;
- return an empty iterable for a valid node with no edges;
- reject an unknown semantic node ID explicitly;
- return deterministic semantic records after adapter normalization;
- expose no repository-file or provider operations.

A backend may use a native edge ID internally and resolve it through an occurrence map. It must not resolve a parallel edge by endpoint pair alone if that lookup is ambiguous.

### 3.4 Separation of responsibilities

| Operation | Allowed work | Prohibited implication |
|---|---|---|
| Projection construction | Build the native graph and identity maps from a validated canonical snapshot | Does not prove native query behavior |
| Full projection inspection | Enumerate all native nodes/edges and validate exact round-trip | Must not be repeated on every bounded query |
| Local adjacency | Ask the native library for incident edges of one reached node | Must not fall back to a full graph scan |
| Semantic traversal | Apply deterministic order, filters, bounds, visited-state, evidence construction | Must not delegate semantic authority to the library |
| Runtime report | Return cached projection metadata plus counters | Must not enumerate the native graph to calculate counts |
| Explicit audit | Re-run full projection validation on request | Must be identified as an audit, not a normal query |

## 4. Direction and edge-occurrence semantics

The following behavior is recommended as the normative contract.

### 4.1 OUTGOING

For node `v`, return each canonical edge occurrence where `source_id == v`, with the traversal neighbor equal to `target_id`.

### 4.2 INCOMING

For node `v`, return each canonical edge occurrence where `target_id == v`, with the traversal neighbor equal to `source_id`.

### 4.3 BOTH

For node `v`, return the union of incoming and outgoing incident edge occurrences. Each canonical occurrence is returned **once**.

A self-loop is both incoming and outgoing by graph-theoretic classification, but it is still one edge occurrence. It must not be counted twice or produce duplicate traversal steps in a single `BOTH` expansion. The current reference implementation appends it through both directional lists; M1 should correct the reference contract and native implementations together, accompanied by independent expected-result tests.

For non-loop directed edges, direction retains its meaning in the edge record. Traversal orientation is represented separately by the current node and selected neighbor; the canonical source and target must not be rewritten.

### 4.4 Parallel edges

Every parallel occurrence remains distinct, even where two or more occurrences have identical source, target and relation. Bounds such as `max_steps` count edge occurrences examined, not distinct neighboring vertices. Evidence de-duplication must not erase the edge-occurrence distinction from traversal steps.

### 4.5 Ordering

The adapter must not rely on undocumented native iteration order. The NetworkX adapter normalizes records with `(traversal_neighbor_id, relation_type, source_id, target_id, occurrence_id)`. The occurrence ID is a canonical edge-sequence index and is therefore snapshot-scoped, not durable across graph rebuilds. The reference traversal uses the same semantic ordering fields; where two edge payloads are byte-for-byte identical, their snapshot occurrence IDs distinguish the occurrences. Tests must assert explicit occurrence identities and expected order within the pinned graph snapshot.

## 5. Capability and acceptance model

A single `lossless` boolean is insufficient for hybrid representations such as SciPy CSR plus side channels. M1 should distinguish **native representation properties** from **end-to-end semantic preservation**.

A descriptive capability record should report at least:

- directedness;
- native parallel-edge support;
- native self-loop support;
- native node/edge attribute support;
- native metadata support;
- semantic edge-occurrence identity support;
- relation-label representation;
- side-channel use and side-channel integrity mechanism;
- supported native adjacency directions;
- serialization/portability limits;
- package/module identity and detected version.

Per-field representation should be able to express states such as:

- `native`;
- `side_channel`;
- `transformed`;
- `unsupported`.

For example, SciPy CSR can report native directed connectivity and multiplicity while relation labels and metadata are provided by exact semantic side channels. SNAP can report canonical JSON string transformation. graph-tool can report in-memory object-valued property maps without claiming portable serialization.

Capabilities are descriptive declarations, not proof of acceptance. The adapter must not set its own production approval state.

### 5.1 Separate environment and conformance states

The runtime and acceptance model must distinguish:

1. implementation present;
2. module discoverable;
3. module importable;
4. required API compatible;
5. version/platform/Python runtime compatible;
6. projection structurally conformant;
7. local adjacency behavior conformant;
8. query semantics conformant;
9. repository-backed behavior conformant;
10. graph-tool routing conformant;
11. production approval for a named runtime/task.

The conformance runner should produce evidence for these states. The selector should consume an explicit accepted state appropriate to the requested operation and environment. Discoverability must not imply compatibility; compatibility must not imply conformance; conformance in one Python/platform environment must not imply conformance in another.

An explicitly requested unavailable or unaccepted backend must fail closed. There must be no silent fallback while reporting the requested backend as active.

## 6. Runtime telemetry contract

Runtime reporting must be observational. It must not cause a full native graph traversal.

At minimum, distinguish:

- `projection_validation_nodes`;
- `projection_validation_edge_occurrences`;
- `native_adjacency_lookups`;
- `native_edge_occurrences_returned`;
- `native_edge_occurrences_validated`;
- `queries_attempted`;
- `queries_succeeded`;
- `queries_failed`;
- `parity_verified_queries`;
- `parity_failures`;
- `total_examined_edge_occurrences`;
- `total_visited_nodes`.

Projection counts should be cached from construction/validation. A call to `runtime_report()` must not invoke `iter_native_nodes()`, `iter_native_edge_occurrences()`, or any full-graph library iterator. If an explicit audit is requested, its work must be separately named and counted.

Counters must be updated at the point where the native API is actually called. They must not be inferred from canonical graph sizes or from requested query parameters.

## 7. M1 conformance test design

A single contract suite should be reusable across every adapter. It must run against real native libraries in their declared environments. Mock/fake modules remain useful for isolated API error-path tests, but cannot be labelled native conformance.

### 7.1 Structural projection tests

- Verify native class/type and directedness.
- Verify node count and exact semantic node mapping.
- Verify edge-occurrence count and unique occurrence mapping.
- Verify parallel edges, including duplicate endpoint/relation combinations.
- Verify self-loops, cycles and isolated nodes.
- Verify all node/edge fields and nested metadata.
- Verify each representation transformation and loss-report field.
- Verify sparse matrix shape, CSR/CSC pointers, indices, values and side-channel multiplicities where applicable.
- Mutate the input graph after construction and prove the adapter snapshot remains consistent.
- Mutate an exported native graph/property and prove the behavior is detected or mutation is prevented.
- Verify construction does not mutate the canonical graph.

### 7.2 Behavioral query tests

For each direction and query-bound dimension, assert explicit expected values for:

- ordered node hits;
- ordered traversal steps;
- exact edge occurrence identities;
- evidence IDs and payloads;
- examined edge count;
- visited node count;
- truncation flag;
- stop reason;
- coverage status.

The fixture must include same-relation parallel edges, different-relation parallel edges, self-loop, cycle, disconnected/isolated node, nested attributes/metadata, Unicode and empty/single-node cases. Add generated cases for multiple insertion orders to prove determinism does not depend on native insertion order.

Run both the independent expected-result assertions and full `TraversalResult` comparison with the Python reference. The expected-result assertions prevent common-mode parity defects.

### 7.3 Native interaction tests

For every backend:

- instrument the library's native per-node adjacency/incident-edge method;
- assert it is called for each reached node in the expected direction;
- assert the returned native edge IDs resolve to the correct semantic occurrence IDs;
- block the full-edge enumerator after construction/one-time validation and prove ordinary bounded traversal still succeeds;
- call `runtime_report()` repeatedly and prove it does not trigger any native graph enumeration;
- assert native adjacency and edge-occurrence counters against independently calculated expected values;
- assert that no whole-graph Python adjacency reconstruction occurs during query execution;
- assert the selected backend name/version matches the actual loaded library.

A test that checks only that `walk()` returns the correct node IDs does not satisfy this layer.

### 7.4 Lifecycle and fault-injection tests

Inject:

- undiscoverable package;
- import exception and shared-library load error;
- missing required native API;
- incompatible API signature/version;
- failed native graph construction;
- missing or duplicate node/edge mapping;
- corrupted native attribute/metadata;
- side-channel mismatch;
- query-time missing native edge;
- native graph mutation after validation;
- invalid direction and unknown node ID.

Verify explicit failure, correct error classification, no partial adapter accepted as usable, no silent fallback, canonical snapshot integrity and no repository/provider/network side effects.

### 7.5 Integration tests

The shared suite must be followed by the repository-backed fixture for each candidate backend. Check each registered tool independently and verify actual backend query deltas. Specifically include:

- `graph_neighbors`;
- `graph_path`;
- graph-backed `find_related_tests`;
- dependency/impact queries;
- `trace_execution_context`;
- `find_workflow_context`.

The last two are current known bypasses and must not receive an overall routing pass until their operations are backend-routed or the conformance report is explicitly scoped to exclude them.

### 7.6 No performance threshold in M1

M1 proves the execution structure: local native adjacency calls occur, global query-time enumeration is absent, and measured counts agree with the fixture. It does not set an arbitrary wall-clock performance threshold.

Comparative speed, memory and scale are M7 concerns. M1 may collect baseline timings, but they are informational until graph sizes, environments and query mixes are controlled.

## 8. Backend-specific implementation obligations after M1

| Backend | Required native query mechanism | Required identity proof |
|---|---|---|
| NetworkX | Per-node `succ` and `pred` keyed adjacency | Reserved edge occurrence field resolves every MultiDiGraph edge key to exactly one canonical occurrence |
| SciPy | CSR row for outgoing; CSC column or justified equivalent for incoming | Matrix pair plus side-channel maps to every occurrence, preserving multiplicity and payload |
| python-igraph | Vertex incident edge-ID index/API for the requested direction | Native EID maps bijectively to semantic occurrence; parallel EIDs remain distinct |
| graph-tool | Native per-vertex incoming/outgoing edge iterators or indexes | Native edge/property-map identity maps bijectively to semantic occurrence |
| SNAP | TNEANet native adjacency/incident-edge APIs in an isolated worker | Native edge ID maps to one semantic occurrence even for parallel endpoint pairs; protocol responses bind to graph fingerprint |

No adapter may pass by emulating this operation with a full scan of its saved Python projection.

## 9. M1 deliverables and exit criteria

M1 acceptance review (2026-11-21):

1. The typed adapter protocol and capability schema are implemented.
2. Direction, parallel-edge, self-loop, edge-occurrence and ordering semantics are explicit and independently asserted.
3. Runtime reporting is observational; projection validation and local query counters are distinct.
4. Structural, behavioral, interaction and mutation/failure-path tests are present in the focused NetworkX contract module.
5. All 18 focused NetworkX contract tests passed in the exact-commit G9.42 full regression run.
6. The tests prohibit full native-edge enumeration and query-time Python reference-adjacency reconstruction; those assertions passed.
7. The targeted E.8.5/E.8.8 test modules passed. The E.8.8 repository-conformance tests invoked the repository runner and asserted a passing report, hash-bound source reads, backend parity and zero context bypasses.

The exact source SHA, test counts, skips, artifact digests and scope limitations are recorded in
[AE-32C M1 NetworkX Validation Record](AE-32C-M1-NetworkX-Validation-Record.md).

**Acceptance boundary:** M1 is accepted for the NetworkX adapter protocol and its tested repository path. This does not mean all registered backends are accepted, nor does it close the separate SciPy/igraph/graph-tool/SNAP native-adjacency milestones. The standalone E.8.5/E.8.8 workflow was not separately dispatched; equivalent NetworkX and repository-runner test assertions were executed under G9.42 on the exact source SHA.

## 10. Non-goals

M1 does not:

- promote SciPy, igraph, graph-tool or SNAP;
- introduce a new graph database or a second semantic source of truth;
- move BFS semantics into third-party libraries;
- lower the project's declared Python version to accommodate SNAP;
- benchmark backends to declare a performance winner;
- treat Graphify links or inferred relationships as native conformance evidence;
- run live provider comparisons before deterministic tests pass.


# AE-32C M4 — python-igraph Native Adjacency Implementation Record

**Status:** Implementation committed; G9.42 validation required  
**Milestone:** M4 — python-igraph native adjacency  
**Target branch:** `stage1/section-uuids` only  
**Predecessor:** M3 accepted by G9.42 run [44898320570](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44898320570), exact Stage1 source SHA `c40a258f627a1678036521e2474fccdd5537e46a`  
**Scope:** python-igraph only. graph-tool and SNAP remain unimplemented for native query adjacency.

## 1. Objective

Replace the generic non-NetworkX full-graph-to-Python-adjacency fallback for python-igraph with native per-vertex incident-edge ID access. Preserve the canonical `SemanticGraph` as the authority for semantic identities, edge occurrence identity, evidence and traversal semantics.

## 2. API selection and technical basis

The adapter uses `igraph.Graph.incident(vertex_id, mode="out"|"in")`, which returns the IDs of edges incident to the selected vertex in the requested direction. This is preferable to neighbor-only APIs because it preserves parallel edge occurrences and exposes stable-within-projection edge IDs for exact side-channel association. The official python-igraph API documents incident-edge access and the edge sequence/edge-ID model ([Graph API](https://python.igraph.org/en/main/api/igraph.Graph.html); [analysis guide](https://python.igraph.org/en/main/analysis.html)).

The implementation does not use `neighbors()` or `get_adjlist()` for query results: those interfaces do not provide the required occurrence-level identity contract.

## 3. Implementation

### 3.1 Native projection and identity

The adapter continues to construct a directed `igraph.Graph` and stores semantic node IDs and complete node payloads as vertex attributes. Each inserted edge receives:
- the canonical semantic occurrence ID;
- relation type;
- attributes;
- metadata.

The projection's insertion order currently maps igraph edge IDs to canonical occurrence IDs one-to-one. Query-time checks validate the edge-ID/occurrence mapping and compare endpoints, relation, attributes and metadata with the immutable projection snapshot before returning a typed `NativeEdgeOccurrence`.

### 3.2 Local adjacency operation

`IGraphAdapter.iter_adjacent_edge_occurrences(node_id, direction)`:
- resolves the semantic node ID to its native vertex index;
- calls `Graph.incident(..., mode="out")` for outgoing adjacency;
- calls `Graph.incident(..., mode="in")` for incoming adjacency;
- unions edge IDs for `BOTH`, preventing a self-loop from being emitted twice;
- expands each selected native edge ID to its exact semantic occurrence and payload;
- rejects invalid IDs, identity mismatches and payload mutation.

Only the incident edge IDs of the requested vertex are read by a query. Parallel edges remain separate because each has its own igraph edge ID.

### 3.3 Traversal and reporting

The shared traversal engine performs the full native projection audit once during construction. Once that audit succeeds, igraph queries use empty Python adjacency indexes and obtain candidates through the native incident-edge API. The deterministic reference traversal remains responsible for BFS ordering, relation filters, depth/step bounds, canonical evidence and per-query parity.

Projection counts are cached from construction. Runtime reporting reads counters and cached counts; it does not enumerate the complete igraph graph. The runtime mode is reported as `igraph_incident_edge_ids`. The registry state is `implemented_unvalidated`, with production approval false.

## 4. Added tests

The E.8.3 test module adds a fake-API contract test covering:
- outgoing and incoming direction;
- two parallel A→B occurrences;
- incoming B→C plus a C→C self-loop in `BOTH`, with the self-loop emitted once;
- exact parity against the reference traversal;
- native lookup and occurrence-read telemetry;
- failure if full native node/edge enumeration is attempted after construction, including during runtime reporting.

The existing conditional real-library test remains the actual python-igraph API smoke/conformance gate when the dependency is installed. A separate conditional repository-runner test now checks all three context operations, native execution-mode labels, native lookup/occurrence telemetry and source follow-through. A fake module is not accepted as proof of binary/API compatibility.

The inspected G9.42 artifact for M3 showed that python-igraph was absent: both real-igraph tests were skipped with the explicit reason `igraph native library is not installed in this interpreter`. Inspection of the G9.42 job log established that the dispatcher installs `source/requirements.txt` directly; it does not install the `graph-core` project extra. Therefore adding igraph only to `pyproject.toml` would not fix the validation environment. The dependency is now included in both the optional `graph-core` extra (for package users) and `requirements.txt` (the exact dependency manifest installed by G9.42). The next G9.42 artifact must confirm that the real tests execute rather than skip.

## 5. Technical limitations and acceptance boundary

This is an implementation milestone, not backend acceptance. In particular:
- The G9.42 environment must actually import python-igraph and execute the real-library test; a skipped test does not qualify M4.
- The exact installed python-igraph version must be present in the validation report/runtime evidence.
- The real native test, complete targeted suite and full regression must pass on the exact Stage1 source SHA.
- Repository-backed conformance must show `igraph_incident_edge_ids` for all required context operations, positive native lookup/occurrence counters, and successful source follow-through.
- Evidence integrity, immutable bundle publication and provenance catalog verification must all pass.
- No performance superiority is claimed; comparative benchmarking belongs to M7.

The fake-adapter test establishes the intended interface behavior only. It does not replace real-library validation. Do not promote igraph to production-approved and do not begin M5 until exact-commit G9.42 acceptance is established.

## 6. Implementation commits

- `f54ea1c3239af9d336ded271a43893bea431323b` — add native incident-edge lookup and occurrence payload validation.
- `bc7c2b003786f463a40d290a96ffa85aa466a1df` — route traversal through igraph native adjacency and cache projection counts.
- `ff94815f5f60b24b471dfc76d16f3a089380a4df` — tighten edge-ID/occurrence mapping validation and registry state.
- `785cddde1b3ed4defd40cc609c7a0c317f18dcd9` — add fake-native adjacency coverage and registry assertions.
- `6fc8b19c55bdbce81429148427c9a92057f470bd` — correct the expected one-time projection read count.
- `0094c6be1b8e47b2b68782c43ee4760b56e43281` — add real-library telemetry assertions and repository context-tool conformance coverage.
- `ed3a2a11d47931848694c32ea16b08845ff3a3c6` — include igraph in the optional `graph-core` validation dependency set.
- `8be9e5d7ecd4475f08c8602d391ce8d424502187` — place real-library assertions in the conditional real-igraph test.
- `992670dba9ff12a48d85f0a97181cbccc1af749e` — align native projection-mutation errors with the traversal integrity contract.
- `8ff22ea2020e86758cad7a5215771d90f6688f0a` — add igraph to the requirements manifest actually installed by G9.42.

No local tests or workflows were run by the implementer. The next step is a user-run G9.42 validation against the latest Stage1 head.


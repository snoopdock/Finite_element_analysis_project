# AE-32C E.8.8.1 — NetworkX Native Adjacency and Repository Conformance

**Status:** implementation prepared; exact-commit G9.42 validation required  
**Target:** `stage1/section-uuids` only  
**Validated parent:** E.8.7.1, Stage1 commit `e01177aeab41936d691f90066dcbd2f4daf29bcc`, G9.42 run `44710472417`  
**Active LLM provider for subsequent live experiments:** OpenRouter  
**Active graph backend:** NetworkX only

## 1. Objective

Establish that the active NetworkX backend does more than exist as an installed package or receive a projection. It must perform native adjacency lookups against the repository-derived semantic graph, return deterministic results matching the canonical Python reference, and surface repository paths that the bounded evidence tool can read from the same source snapshot.

This increment deliberately keeps NetworkX as the only active live backend. It does not enable SciPy, igraph, graph-tool or SNAP for live evaluation.

## 2. Evidence from the last successful OpenRouter live run

OpenRouter run `44712565739` used Stage1 commit `e01177aeab41936d691f90066dcbd2f4daf29bcc` and reported:

- NetworkX 3.6.1 as the active computation backend;
- a directed `MultiDiGraph` projection of 26 nodes and 41 edge occurrences;
- three successful backend queries and three reference-parity checks;
- zero parity failures;
- six visited nodes and three examined edges;
- graph-surfaced source paths `main.py`, `pipeline/extractor.py` and `tests/checks.py`;
- complete, hash-matching reads of `main.py` and `tests/checks.py` after graph discovery.

The report also shows that the LLM requested `find_related_tests` and several source reads. The required `graph_neighbors` query was orchestrator-prefetched, not selected by the model. The report must preserve that distinction: the LLM used graph-derived tools, but did not itself request the core `graph_neighbors` query in that run.

## 3. Native adjacency change

Before this increment, `NetworkXGraphTraversalEngine._build_adjacency()` iterated over every edge in the NetworkX `MultiDiGraph` for every query, validated the projection, and reconstructed Python adjacency dictionaries. This was correct under parity checks but did unnecessary whole-graph work for each bounded query.

The revised engine:

1. validates the complete NetworkX projection once at construction;
2. keeps the canonical `SemanticGraph` and its ordered edge occurrences as the evidence authority;
3. obtains outgoing neighbors from NetworkX `MultiDiGraph.succ[node]`;
4. obtains incoming neighbors from NetworkX `MultiDiGraph.pred[node]`;
5. resolves each native edge occurrence back to the canonical `SemanticEdge` and validates endpoints, relation, attributes and metadata before accepting it;
6. keeps deterministic AE-32 BFS ordering, bounds, evidence construction and per-query reference parity.

This is an intentional hybrid: NetworkX supplies native indexed adjacency access; AE-32 retains the deterministic BFS control and evidence semantics. The implementation does not claim that NetworkX's own `bfs_edges()` algorithm is being used.

New runtime counters distinguish:

- `native_adjacency_lookups`;
- `native_edge_occurrences_read`;
- `projection_validation_nodes`;
- `projection_validation_edge_occurrences`.

A test disables the full `MultiDiGraph.edges` view after construction and verifies that the query still succeeds through `succ`/`pred`, while matching the reference traversal exactly.

## 4. Repository-backed conformance

The new runner `tools/gb04_repository_backend_conformance.py` uses the controlled incident repository fixture rather than an in-memory graph alone.

It verifies:

1. complete repository evidence indexing;
2. the required incoming `CALLS` query for `symbol:pipeline.extractor::extract`;
3. the expected source paths `main.py` and `tests/checks.py`;
4. complete bounded reads of both surfaced files through `read_source_file`;
5. exact equality between graph-recorded and read-source SHA-256 values;
6. a source-to-target graph path query;
7. related-test discovery;
8. at least three backend/reference parity-verified graph queries;
9. no repository-code execution, provider calls, network calls or source modifications.

The fixture currently contains nine indexed files, 26 graph nodes and 41 edge occurrences. The runner does not call OpenRouter or any other provider.

## 5. Important architecture boundary: graph backend versus repository file access

The graph library should not open arbitrary repository paths itself.

The intended flow is:

```text
Repository snapshot
    -> deterministic source index and source hashes
    -> canonical SemanticGraph
    -> selected native graph projection (NetworkX)
    -> bounded graph query requested by the LLM or orchestrator
    -> graph result containing source paths, line metadata and hashes
    -> read_source_file validates the path and reads the same snapshot
    -> evidence ledger records the read and provenance
    -> LLM interprets the returned evidence
```

This gives every future backend the same repository graph and the same file-evidence boundary. A backend is not allowed to bypass path validation, read arbitrary files, modify the repository or execute repository code.

The LLM guides the investigation by requesting registered graph and source tools. Backend selection remains trusted workflow configuration; the model cannot silently change the backend or interpreter.

## 6. Current integration gap discovered

The new repository runner explicitly records two graph-derived tool families that still use bounded walks over the canonical `SemanticGraph` rather than the selected backend query service:

- `trace_execution_context`;
- `find_workflow_context`.

The following operations already use the selected backend query path:

- `graph_neighbors`;
- `graph_path`;
- graph-backed portions of `find_related_tests`;
- dependency and impact queries.

This means E.8.8.1 establishes repository-backed NetworkX use, but it does not yet claim that every graph-derived tool is routed through NetworkX. E.8.8.2 should migrate the two remaining context walks to backend-independent `GraphQuery` operations while preserving their type-checking-import exclusions, source-line provenance, depth bounds and output schema.

## 7. Other backends — staged acceptance plan

NetworkX remains the only live backend until its repository-backed query path and tool routing are complete.

| Increment | Backend | Acceptance focus |
|---|---|---|
| E.8.8.1 | NetworkX | Native adjacency, repository graph queries, hash-bound source reads |
| E.8.8.2 | NetworkX | Route context and workflow graph walks through the selected backend service |
| E.8.8.3 | SciPy | CSR/CSC native adjacency and repository-level parity |
| E.8.8.4 | igraph | Native incident-edge/adjacency queries and repository-level parity |
| E.8.8.5 | graph-tool | Native vertex/edge adjacency queries and repository-level parity |
| E.8.8.6 | SNAP | Isolated worker compatibility and repository-level parity |
| E.8.9 | All accepted backends | Controlled OpenRouter comparison using identical repository snapshots and investigation budgets |

Every backend must pass both the synthetic adversarial multigraph contract and the repository-backed conformance runner. Passing fake-module tests, importing a package, or projecting a graph is not native acceptance.

## 8. Python environments

NetworkX, SciPy, igraph and graph-tool can be tested in isolated Python 3.11 environments for this project. The current igraph documentation recommends binary installation and provides wheels for recent Python minor versions; graph-tool is best provisioned through its Conda-forge environment. SciPy's CSR representation supports efficient row access, while CSC is appropriate for incoming-column access.

SNAP is different. Stanford's published Snap.py 6.0 wheels include CPython 3.9 builds and were uploaded in December 2020. Python 3.9 is end-of-life. Do not lower the main AE-32C runtime to Python 3.9. The intended route is a restricted Python 3.9 worker with no provider credentials, no network access and read-only graph snapshot input, communicating with the Python 3.11 orchestrator through a bounded JSON-lines protocol. SNAP is not accepted until that worker returns results that pass canonical reference parity.

## 9. LLM guidance and deterministic authority

- OpenRouter remains the live provider for this phase.
- The LLM can choose among registered read-only investigation tools and supply bounded query arguments.
- The orchestrator validates every tool call and enforces depth, result, node and traversal budgets.
- The selected backend executes graph adjacency operations.
- The canonical reference traversal independently checks each accepted result.
- Source reads are separately validated against the repository snapshot and hashes.
- The LLM cannot choose arbitrary Python code, shell commands, backend libraries, Python interpreters, filesystem paths outside the repository, or repository modifications.
- Diagnostic accuracy remains `not_assessed` unless a registered deterministic reproduction or other approved machine-verification procedure establishes it. Human review is not required by the current project policy.

## 10. Validation requirements

For this increment:

1. New NetworkX adjacency tests pass.
2. Repository-backed graph-to-file conformance passes.
3. Existing E.8.7.1 targeted tests pass.
4. G9.42 passes on the exact Stage1 commit.
5. Full regression passes on that same commit.
6. Detached evidence and provenance verification pass.
7. A subsequent OpenRouter live run reports NetworkX as active and records native adjacency counters.

No claim of full multi-backend acceptance is made by this increment.

## 11. External references

- NetworkX `MultiDiGraph.successors` and indexed `succ`/`pred` adjacency: https://networkx.org/documentation/stable/reference/classes/generated/networkx.MultiDiGraph.successors.html and https://networkx.org/documentation/latest/reference/classes/generated/networkx.MultiDiGraph.succ.html
- SciPy CSR row storage and efficient row slicing: https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csr_matrix.html
- python-igraph installation and current Python support: https://python.igraph.org/en/latest/install.html
- graph-tool `GraphView` and native adjacency methods: https://graph-tool.skewed.de/static/docs/stable/autosummary/graph_tool.GraphView.html and https://graph-tool.skewed.de/static/docs/stable/autosummary/graph_tool.Vertex.html
- SNAP TNEANet directed multigraph and node iterator APIs: https://snap.stanford.edu/snappy/doc/reference/graphs.html
- SNAP 6.0 CPython 3.9 wheel metadata: https://pypi.org/project/snap-stanford/

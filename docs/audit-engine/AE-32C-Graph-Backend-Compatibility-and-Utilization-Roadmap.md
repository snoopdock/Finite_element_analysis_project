# AE-32C — Graph Backend Compatibility and Utilization Roadmap

**Status:** M0 closed; M1 typed protocol and NetworkX-first implementation committed; exact-commit validation and remaining M1 gates pending  
**Target branch:** `stage1/section-uuids` only  
**Initial baseline reviewed:** `5a881c57cafc9ff17c3e01d3e1401ea9daf49225` — `AE-32C E.8.8.1`  
**Current M0 close-out snapshot:** `1ed0471832b660e8c29a946e4655e1ed981106bf` — `E.8.8.2`; G9.42 run `44885166907`  
**M1 implementation snapshot:** `3003e2c599e70f14d7656f85fac128cf66d38b0b` — typed protocol, NetworkX traversal routed through adapter adjacency, `BOTH` self-loop correction, explicit conformance states, and cached observational runtime counts; validation not run  
**Scope:** Semantic graph adapters, native-library compatibility, traversal behavior, graph-tool routing, repository-backed conformance and later runtime utilization  
**Change policy:** No branch creation, no work on `main`, no history rewriting, and no backend promotion without evidence-based acceptance.

---

## 1. Executive position

The project has progressed beyond placeholder adapters. It has a canonical `SemanticGraph`, projection code for five computational backends, a deterministic Python reference traversal, a NetworkX-native query path, a native conformance fixture, and a repository-backed conformance runner.

However, the existence of an adapter, the ability to construct a native graph, and an exact result match on a small fixture do **not** establish that the library is being used in the intended way or that its adapter is robust in the repository's real execution path.

The principal current distinction is:

- **NetworkX:** the strongest integration. The E.8.8.1 record describes complete projection validation followed by node-local access through `MultiDiGraph.succ` and `pred`, while AE-32 retains deterministic BFS ordering, evidence construction and parity checking.
- **SciPy, igraph, graph-tool and SNAP:** projection/readback support exists, but the shared non-NetworkX traversal path currently enumerates the complete native node and edge sets and reconstructs Python adjacency dictionaries. That is not yet the intended per-query, native-adjacency execution model.
- **Graph-tool routing:** not every graph-derived evidence tool uses the selected backend. E.8.8.1 explicitly records that `trace_execution_context` and `find_workflow_context` still perform bounded walks over the canonical graph.
- **Acceptance state:** package discoverability and a hard-coded `semantic_traversal` capability are weaker than a proven, version-compatible, behaviorally conformant native adapter. These states must be separated.

The next step is therefore not to add more adapters or to start a live LLM experiment. It is to make the adapter contract, its structural invariants, its observable behavior and its acceptance evidence precise. We will then qualify each backend individually.

## 2. Where the architecture stands

### 2.1 Authority and data flow

The canonical semantic graph remains the source of truth. A backend is a computational projection, not an authority over semantic identities, evidence, provenance or repository files.

The intended boundary is:

```text
Repository snapshot
    -> deterministic evidence/source index
    -> canonical SemanticGraph
    -> selected backend projection
    -> bounded graph query
    -> canonical semantic edge occurrences and evidence
    -> validated source-file follow-through
    -> investigator / LLM interpretation
```

A backend may provide native adjacency and computation. AE-32 retains query validation, deterministic ordering, bounds, provenance/evidence interpretation and the reference comparison. A backend must not read arbitrary repository paths, execute repository code, make provider calls or modify repository content.

### 2.2 Adapter contract gap

The current abstract `SemanticGraphAdapter` requires only:

- `export()`
- `capabilities()`
- `identity_mapping()`
- `loss_report()`

Traversal also expects `iter_native_nodes()` and `iter_native_edges()`, which are not part of the abstract interface. A class can therefore satisfy the formal base class while still failing the runtime expectations of the traversal layer.

The shared `NativeAdapterMixin.neighbors()` implementation scans the stored Python projection and returns distinct neighbor IDs. It does not establish native per-node adjacency access and it does not preserve individual parallel edge occurrences as query results.

**Required direction:** define one typed, backend-independent adapter contract for native projection inspection and exact per-node adjacency. The adjacency operation must return edge-occurrence records, not merely neighboring node IDs. It must express direction and preserve the canonical occurrence identity, endpoints, relation, attributes and metadata needed by the query service.

The complete projection audit and the query-time adjacency operation should remain separate:

1. A **projection conformance operation** may inspect the complete native graph during construction or an explicit audit.
2. A **query adjacency operation** must inspect only the native adjacency of reached nodes and must not silently rebuild the whole graph for each query.

### 2.3 Availability is not acceptance

Current code uses `find_spec()` to establish package discoverability and checks a small number of symbols after import. The capability registry marks several optional backends as `semantic_traversal=True` independently of whether their real API and behavior have passed native conformance.

We will separate at least these states:

1. adapter implementation present;
2. package discoverable;
3. package importable in the declared environment;
4. required API/version compatible;
5. projection structurally conformant;
6. native adjacency behavior conformant;
7. canonical query semantics conformant;
8. repository-backed graph/evidence behavior conformant;
9. integrated graph-derived tools routed through the selected backend;
10. explicitly approved for the intended runtime.

Normal selection must fail closed unless the required states for that environment and task have been established. There must be no silent fallback to Python traversal while reporting the optional backend as active.

## 3. Current backend position

| Backend | Current implementation position | Main gap before acceptance |
|---|---|---|
| NetworkX | Native `MultiDiGraph`; E.8.8.1 describes per-node `succ`/`pred` access, occurrence mapping and canonical parity | Verify exact-commit structural tests, finish tool routing, verify mutation isolation and repository-level behavior |
| SciPy | Hybrid CSR connectivity plus exact semantic edge side channels | Query-time CSR row access for outgoing and CSC column access for incoming; occurrence-level joins; structural proof that whole-graph enumeration is not used |
| python-igraph | Directed native graph with vertex/edge attributes and semantic occurrence IDs | Use native incident-edge indexes (for example, edge-ID lists) for reached vertices; verify parallel-edge identity and direction |
| graph-tool | Directed native graph with vertex/edge property maps | Use native vertex in/out edge iterators or indexes; prove exact occurrence identity and property-map semantics in the supported environment |
| SNAP | TNEANet projection with JSON-encoded attributes | Treat CPython 3.9 as an isolated worker candidate, not project-runtime acceptance; implement bounded worker protocol and prove exact parallel-edge association |
| RDFLib | Separate RDF interchange/SPARQL subsystem | Keep outside the five-backend traversal matrix unless a separate architectural decision changes the scope |

SciPy's matrix representation does not itself contain all semantic edge metadata; the hybrid design must be assessed as a complete adapter, including side channels. SNAP's JSON serialization is a representation transformation and must be explicitly tested and reported. Graph-tool's object-valued property maps are in-memory structures and must not be described as portable serialized graph data.

## 4. Testing policy — structural, behavioral and interaction evidence

This project will not accept an adapter based only on a test that feeds it a graph and compares a returned traversal result. Input/output parity is necessary, but insufficient.

The test strategy must establish **what the adapter is**, **what it does**, **how it interacts with the native library**, **which path the application actually executes**, and **what it does when assumptions fail**.

### 4.1 Layer A — structural contract tests

Verify the actual native representation and its invariants, not just the adapter's reported capability dictionary.

Required checks include:

- correct native graph class and directedness;
- parallel-edge and self-loop representation;
- one-to-one semantic-node identity mapping;
- one-to-one edge-occurrence mapping, including parallel edges with identical endpoints and relation labels;
- no missing, duplicated or silently collapsed nodes/edge occurrences;
- complete node and edge attributes, relation labels and metadata;
- exact side-channel/native-payload association where the library cannot natively represent the complete semantic payload;
- matrix shape, index arrays, pointer/index consistency and multiplicity for sparse representations;
- explicit type/serialization transformations and loss reports;
- snapshot isolation: later mutation of the caller's canonical graph must not mutate the adapter's source snapshot, and mutation of returned mutable objects must not unexpectedly mutate canonical data;
- adapter construction and export do not mutate the canonical graph.

Tests must inspect the resulting native object and its occurrence/index maps. A method returning `lossless=True` is not proof that the projection is lossless.

### 4.2 Layer B — behavioral contract tests

Use independent, explicit expected outcomes in addition to differential comparison with the Python reference engine.

Cover:

- outgoing, incoming and bidirectional traversal;
- multiple parallel edges, including identical relation labels;
- self-loops, cycles, isolated nodes and disconnected components;
- relation filters and combinations of filters;
- depth, visited-node, result and examined-step bounds;
- deterministic ordering and repeatability;
- exact evidence payloads and edge occurrence identities;
- stop reason, truncation and coverage status;
- invalid and unknown node identifiers;
- empty graphs, singleton graphs and high-degree nodes;
- stale canonical snapshots and corrupted native projections;
- exception propagation and fail-closed behavior.

The reference traversal remains a valuable differential oracle, but it must not be the only oracle. If the native and reference paths share an erroneous semantic assumption, exact parity can reproduce the same defect. The test suite must assert independently specified expected results for critical cases.

**Open semantic point:** bidirectional traversal around a self-loop must have a written occurrence-counting rule. The tests must assert that rule directly rather than merely copying whatever the current reference implementation happens to do.

### 4.3 Layer C — native-library interaction and execution-path tests

These tests establish that a backend is genuinely used when the application claims it is active.

Examples:

- instrument or spy on the backend's native adjacency API and prove it is called for reached nodes;
- disable or make the full-graph edge enumerator fail after the one-time projection audit, then prove bounded queries still work;
- prove outgoing and incoming queries use the correct native adjacency direction;
- prove the returned records map back to exact canonical edge occurrences;
- assert native adjacency counters, edge-occurrence read counts and reference-parity counters against independently known expected values;
- prove query-time work is tied to reached-node adjacency rather than a repeated full-node/full-edge scan;
- assert that no generic Python adjacency fallback is used while the runtime reports a native backend;
- assert that explicit backend selection either uses that backend or fails; it must not silently change backends;
- test all relevant registered graph tools, not only a single low-level traversal method.

Do not overfit tests to private method names when an observable contract is available. It is appropriate, however, to instrument a concrete library API when the architectural claim is specifically that the adapter uses that API.

### 4.4 Layer D — lifecycle, fault-injection and side-effect tests

Exercise the adapter under failure and mutation, not only on a valid happy path.

Include missing packages, import errors, incompatible versions, missing API methods, malformed native objects, failed projection construction, corrupted attributes, duplicate/missing occurrence IDs, invalid side-channel references, and failures during a query.

Verify:

- errors are explicit and actionable;
- partially built state is not exposed as a usable adapter;
- backend selection fails closed;
- canonical graph and repository files remain unchanged;
- provider calls and network access remain absent from deterministic conformance runners;
- no repository code is executed by graph construction or query tests;
- optional libraries are imported lazily where the architecture requires it.

### 4.5 Layer E — repository-backed integration tests

Synthetic graph fixtures are necessary but do not prove repository behavior. Each backend promoted beyond the synthetic stage must also run the controlled repository fixture and demonstrate:

- complete evidence indexing;
- required graph relationships and source paths;
- graph query results and paths;
- graph-to-source follow-through;
- source hashes matching the graph evidence snapshot;
- related-test discovery;
- selected backend and native API counters for each routed operation;
- no repository-code execution, provider calls, network calls or source modifications.

The test must distinguish a result prefetched by the orchestrator from an operation actually requested by the investigator/LLM. These are different integration claims.

### 4.6 Layer F — controlled live evaluation

Only after deterministic structural, behavioral, interaction and repository-backed gates pass should we use live provider experiments.

A live report must make it possible to answer:

- Which backend was selected, and which native library/version was loaded?
- Which graph-derived tools were invoked?
- Which tool calls were selected by the model, and which were prefetched by orchestration?
- Which native adjacency APIs were used, on which reached nodes, and for how many edge occurrences?
- Were reference-parity checks run and passed?
- Did graph-surfaced paths lead to complete, hash-matching source reads?
- Were bounds, exclusions and failure policies respected?
- Were there provider, network, filesystem or repository side effects outside the declared policy?

A live LLM response that looks plausible is not an adapter conformance result. Diagnostic correctness, tool-selection quality and backend correctness must be measured as separate outcomes.

## 5. Acceptance rule

A backend is not accepted merely because its import succeeds, a graph object can be constructed, or one traversal result matches the reference.

The minimum promotion gates are:

1. **Environment gate:** declared Python/platform and dependency versions are installed and recorded.
2. **Structure gate:** actual native graph and identity/occurrence structures satisfy the adapter contract.
3. **Projection gate:** exact canonical-to-native-to-canonical readback, including every edge occurrence and payload.
4. **Behavior gate:** independent expected results and reference parity pass across the adversarial query matrix.
5. **Interaction gate:** tests prove native per-node adjacency APIs are called and whole-graph query-time readback/fallback is absent.
6. **Lifecycle gate:** fault injection, immutability, isolation and fail-closed tests pass.
7. **Repository gate:** graph query, evidence provenance and source follow-through pass on the controlled repository fixture.
8. **Tool-routing gate:** every in-scope graph-derived tool either uses the selected backend or has an explicit documented exception.
9. **CI gate:** all applicable tests pass on the exact Stage1 commit; skips are reported as skips, not passes.
10. **Operational gate:** controlled live evidence confirms the runtime path and usage telemetry without conflating model behavior with deterministic correctness.
11. **Approval gate:** only then may the backend be promoted for the specified runtime and task.

Performance is measured only after correctness and actual native usage are demonstrated. Benchmarking must compare equivalent semantics and include graph construction, projection memory, query setup, adjacency access, traversal, evidence reconstruction and end-to-end query cost.

## 6. Milestone roadmap

### M0 — Architecture baseline and traceability

**Purpose:** freeze what exists before changing adapter code.

Work:
- pin the reviewed Stage1 commit and inventory relevant modules, tests, workflows and ADRs;
- map each adapter from factory/registry through projection, query, evidence construction and tool entry point;
- distinguish implemented, tested, native-tested, repository-tested and live-used behavior;
- map each architectural statement in ADR-008 onward to implementation and test evidence;
- reconcile duplicate ADR identifiers, the effectively empty ADR-016 and the ADR-079 title/identifier mismatch;
- identify the exact tests and workflows that support each claim.

**Exit:** a traceable adapter matrix with evidence references, unresolved questions and no claims based solely on documentation.

### M1 — Formal adapter contract and capability/acceptance model

**Purpose:** eliminate implicit duck-typed runtime requirements.

Work:
- formalize native node/edge inspection and per-node exact-edge adjacency in the typed interface;
- define direction, self-loop, parallel-edge and edge-occurrence semantics;
- separate native representation capabilities from end-to-end semantic preservation;
- replace availability-only promotion with explicit compatibility and conformance states;
- define runtime reports that distinguish projection audit work from query-time native adjacency work;
- write structural, behavioral and interaction contract tests before implementation changes.

**Exit:** a backend-neutral protocol specification and a failing/passing conformance suite that can be applied to each adapter.

### M2 — Complete NetworkX and graph-tool routing

**Purpose:** finish the strongest adapter first and establish a reference-quality integration pattern.

Work:
- verify E.8.8.1 native `succ`/`pred` access and its tests at the exact baseline;
- prove occurrence-level parity, self-loop handling, deterministic ordering and defensive-copy behavior;
- route `trace_execution_context` and `find_workflow_context` through backend-independent `GraphQuery` operations;
- preserve type-checking import exclusions, bounds, line provenance, evidence shape and error behavior;
- expand repository conformance so each in-scope graph tool is checked for backend query deltas.

**Exit:** NetworkX passes all structural, behavior, interaction and repository gates; no undocumented graph-tool bypass remains.

### M3 — SciPy native sparse adjacency

**Purpose:** use the sparse representation for actual query access.

Work:
- CSR row-based outgoing adjacency;
- CSC column-based incoming adjacency, or a measured and justified alternative;
- exact pair-to-occurrence side-channel joins for parallel edges and same-label duplicate occurrences;
- matrix structure and side-channel consistency checks;
- tests that forbid full edge readback during query execution;
- repository-backed parity and bounded access tests.

**Exit:** SciPy passes the same acceptance gates as NetworkX, with native sparse access demonstrated by instrumentation.

### M4 — python-igraph native adjacency

**Purpose:** use native incident-edge indexes rather than full edge enumeration.

Work:
- investigate and use edge-ID-returning incident/incoming/outgoing APIs;
- preserve edge IDs and semantic occurrence IDs across parallel edges;
- test direction filtering, self-loops, vertex identity mapping and attribute round trips;
- run native and repository-backed tests in the declared Python 3.11 environment.

**Exit:** exact occurrence-level native adjacency and all shared acceptance gates pass.

### M5 — graph-tool native adjacency

**Purpose:** qualify graph-tool's native vertex/edge iteration and property-map model.

Work:
- use per-vertex incoming/outgoing edge iterators or equivalent indexed APIs;
- verify property-map types, object-valued payload behavior and mutation semantics;
- test parallel edges, self-loops, semantic IDs and occurrence identity;
- use a reproducible supported graph-tool environment and record exact versions.

**Exit:** graph-tool passes all shared acceptance gates in its supported environment; serialization limitations remain explicit.

### M6 — SNAP isolated worker and compatibility

**Purpose:** qualify SNAP without weakening the main project's runtime.

Work:
- keep the main orchestrator on the declared Python runtime;
- verify the Python 3.9 SNAP candidate in a restricted worker;
- define a bounded, versioned JSON-lines protocol and strict input/output schemas;
- pass only an immutable graph snapshot and bounded query request;
- prove exact edge-ID/semantic-occurrence association, especially with parallel edges;
- enforce no provider credentials, repository access, network access or write access in the worker;
- validate returned results against the canonical Python reference in the orchestrator.

**Exit:** isolated worker protocol and repository-level parity pass. A Python 3.9 import smoke test alone is not acceptance.

### M7 — Comparative performance and promotion policy

**Purpose:** determine whether native adapters provide useful operational value.

Work:
- benchmark equivalent graph snapshots and query matrices;
- measure construction time, peak memory, projection size, one-time validation cost, native adjacency calls, edge occurrences inspected, traversal time and end-to-end result time;
- test sparse/dense, small/large, low/high-degree and different query-bound distributions;
- record warm/cold behavior and environment versions;
- promote backends only for workloads where correctness is accepted and performance/operational trade-offs are measured.

**Exit:** reproducible benchmark dossier and explicit per-backend/task approval policy. No assumed winner.

### M8 — Full repository graph interaction audit

**Purpose:** after the adapters themselves are trustworthy, audit how the graph represents and connects the repository.

Work:
- inspect source inventory, symbol/import/call edges, dynamic imports and framework entry points;
- examine graph coverage and false-positive/false-negative patterns;
- validate test and workflow links, dependency/impact paths and source provenance;
- compare graph-derived findings with independent source-level evidence;
- inspect LLM tool selection and evidence follow-through using the accepted backend;
- use Graphify for navigation and candidate discovery, not as the correctness authority.

**Exit:** a source-backed map of graph coverage, graph/runtime interactions, omissions and known limitations.

## 7. Graphify policy and current freshness

Graphify is useful for navigation: locating hubs, candidate modules, symbol relationships and possible call/import paths. It is not evidence that a native adapter executes, that an edge is correct, or that a live tool uses a particular library.

The latest available Stage1 Graphify report inspected during this review identifies its source as commit `f55f10d5`. The baseline used for this roadmap is `5a881c57cafc9ff17c3e01d3e1401ea9daf49225`; therefore that report is not accepted as a current snapshot. The report may be used only as a navigation hint until regenerated from the pinned Stage1 commit.

The Graphify workflow and its runner are not present on `stage1/section-uuids`. A remote clone attempt from this execution environment could not resolve `github.com`, and the available GitHub actions do not expose a workflow-dispatch operation. No workflow was triggered and no Graphify artifact was written to another branch. Refresh Graphify locally or add a branch-local, explicitly scoped runner in a later task; do not make a run that publishes to `main` as part of this work.

## 8. Initial M0 findings and open checks

Confirmed in the Stage1 source/documentation reviewed for this roadmap:

- E.8.8.1 describes NetworkX's one-time complete projection validation followed by native indexed `succ`/`pred` adjacency for reached nodes.
- E.8.8.1 identifies `trace_execution_context` and `find_workflow_context` as not yet backend-routed.
- `SemanticGraphAdapter` does not formally declare the native iteration/adjacency methods required by traversal.
- `NativeAdapterGraphTraversalEngine` performs complete native node/edge readback to reconstruct adjacency; this happens at construction and is the current non-NetworkX traversal design.
- The capability registry's package availability and `semantic_traversal` flags do not encode the full conformance ladder.
- The E.8.5 fixture already covers directed edges, parallel edge occurrences, a self-loop, a cycle, an isolated node, nested attributes and seven query cases repeated twice.
- The E.8.5 test asserts native round-trip and reference-parity results when the library is installed. Those tests are valuable, but the new policy additionally requires structural invariants, native API interaction proof, lifecycle/fault injection and per-tool runtime routing evidence.
- The E.8.8.1 repository runner reports the two known tool-routing exceptions, but currently returns an overall `status: passed` when those operations remain canonical-graph walks. Acceptance summaries must preserve that scope limitation; a passing scoped runner is not evidence that every graph tool is backend-routed.
- The E.8.5/E.8.8 native workflow is manually dispatched. The combined commit status lookup for the reviewed baseline returned no status entries in this audit. This is not evidence of a passing current-commit CI run.

Checks still required to close M0:
- locate and inspect the exact E.8.8.1 NetworkX anti-full-enumeration test and its invocation in the workflow;
- map the adapter factory and all registered graph tools to backend query services;
- inspect every backend adapter's native API/version assumptions and its existing tests;
- verify current workflow job conditions, artifacts and exact-commit evidence;
- reconcile ADR identifiers/statuses and the implementation/test links;
- record the actual dependency versions and supported platforms for each native backend.



## 9. M0 traceability findings from the source pass

The following findings refine the initial inventory. They are based on the source files at the reviewed Stage1 snapshot, not on Graphify inference.

### 9.1 Factory and service wiring

- `BackendFactory` contains a lazy module/class registry for NetworkX, SciPy, igraph, graph-tool and SNAP. It imports the selected adapter class and constructs it from the supplied execution context.
- `BackendPipeline.execute()` selects a candidate using the registry, creates the adapter and records projection provenance/transformation/loss assessment. It does not itself verify API version compatibility or a conformance state.
- `RepositoryEvidenceTools` constructs `SemanticGraphAnalysisService` with the configured `graph_backend` and `verify_backend_parity=True`. Its runtime report identifies the selected engine and execution counters. This confirms the service-level wiring exists; it does not establish that every individual graph tool actually invokes that engine.
- The backend remains configuration selected, not selected by LLM tool arguments. This is consistent with ADR-045.

### 9.2 Full-read behavior in the non-NetworkX path

The source confirms a significant interaction/performance issue:

1. `NativeAdapterGraphTraversalEngine.__init__()` calls `_build_adjacency()` to validate the native projection.
2. Each `walk()` calls the inherited traversal implementation, which calls `_build_adjacency()` again.
3. The non-NetworkX `_build_adjacency()` materializes all values from `iter_native_nodes()` and `iter_native_edges()`, validates them, and reconstructs Python outgoing/incoming dictionaries.
4. `runtime_report()` independently materializes `iter_native_nodes()` and `iter_native_edges()` again to calculate projection counts.

Consequently, non-NetworkX queries do not yet use native, reached-node adjacency. Runtime reporting can also cause additional complete native graph reads. The latter reads are not represented by the same `native_projection_reads` counter used by `_build_adjacency()`, so telemetry can under-report actual native enumeration.

The M1/M3–M6 tests must prove that full enumeration is limited to explicit projection audit/construction and that ordinary query execution and runtime reporting do not trigger hidden full scans.

### 9.3 Adapter-specific observations

- **NetworkX:** `NetworkXGraphTraversalEngine` validates the full projection at construction and reads node-local `succ`/`pred` adjacency during queries. It maps native edge data back to the canonical edge tuple by a reserved occurrence field. `NetworkXAdapter` itself assigns node/edge attribute and metadata dictionaries from its input graph without independently deep-copying them. The traversal engine clones the validated graph before constructing the adapter, but direct adapter use still deserves snapshot-isolation tests.
- **SciPy:** `SciPyAdapter.iter_native_edges()` walks all CSR rows and joins each matrix pair to its exact occurrence side channels. That is appropriate for a complete projection audit, but it is not a local adjacency query. Its current `neighbors()` method reads a CSR row, but returns distinct neighbor node IDs, not exact edge occurrences with their semantic payloads; it is not yet the traversal contract.
- **igraph and graph-tool:** both preserve semantic occurrence identifiers as edge attributes/property maps, but their current `iter_native_edges()` methods enumerate the complete native edge set. Their native incident-edge/vertex adjacency APIs are not yet exposed through the common adapter interface.
- **SNAP:** the adapter preserves occurrence identity and stores nested attributes/metadata as canonical JSON strings, but its readback method also iterates the complete edge set. Exact node-local edge retrieval and occurrence mapping under parallel edges remain to be established.

### 9.4 Current conformance coverage and its boundary

The inspected E.8.5 test module verifies fixture structure (five nodes, eight directed edge occurrences, three parallel edges between one pair, one self-loop and Unicode values) and, when a real library is installed, checks projection round-trip, seven query cases repeated twice, 14 reference-parity checks, zero query/parity failures, and no provider/network calls.

This is a sound base. It does not by itself prove that the adapter invokes the intended native local-adjacency API, that query-time whole-graph enumeration is absent, that runtime reporting is observational rather than computational, or that every graph-derived evidence tool is routed through the backend. The expanded Layer A–F test policy above is intended to close those gaps.

The deterministic reference traversal currently builds both outgoing and incoming candidate lists for a `BOTH` query. A self-loop is therefore included once through each list. The traversal loop appends a step and increments `examined_edges` before checking whether the neighbor was already visited; the self-loop can consequently appear twice in `steps` and be counted twice, although its evidence record is deduplicated by evidence ID. This is an observed reference behavior, not yet a settled contract. M1 must decide whether `BOTH` means one visit per edge occurrence (recommended) or preserves this double observation, then test the decision independently and update the reference and native paths together.

### 9.5 CI evidence boundary

The E.8.5/E.8.8 workflow is manually dispatched. It provisions NetworkX/SciPy/igraph in Python 3.11, graph-tool in its Conda environment, and a separate Python 3.9 SNAP compatibility smoke. Its summary correctly says the SNAP smoke is not adapter acceptance and requires synthetic plus repository reports for the other backends.

The reviewed baseline's combined commit status query returned an empty status list. No exact-commit CI result was established in this source pass. Do not infer a pass from the workflow file existing or from older local test records.


### 9.6 Existing test coverage — what is already strong

The existing suite contains meaningful structural, behavioral and integration checks. This roadmap does not discard them or describe the project as having only input/output tests.

| Test file | Current evidence already covered | Remaining limitation relevant to this roadmap |
|---|---|---|
| [test_e82_networkx_traversal_backend.py](../../tests/semantic_graph/test_e82_networkx_traversal_backend.py) | Native object is a directed MultiDiGraph; node/edge counts and three parallel edges; canonical graph unchanged after projection; backend/reference parity across directions, depths and relation filters; fail-closed behavior when canonical graph changes or contains a dangling edge; service-level selected-backend metadata | Self-loop behavior is compared to the reference, not asserted against an independent expected occurrence count. It does not test every native adjacency API or runtime-report side effects. |
| [test_e88_networkx_repository_backend.py](../../tests/semantic_graph/test_e88_networkx_repository_backend.py) | Query path explicitly forbids full NetworkX `edges` enumeration after construction; checks native successor/predecessor mode and adjacency/read counters; repository graph-to-source reads are hash-bound; runner reports current context/workflow routing exceptions; snapshot and side-effect declarations are checked | The anti-full-scan proof is NetworkX-specific. No corresponding per-node-native-adjacency proof exists for SciPy, igraph, graph-tool or SNAP. The repository runner's overall `passed` status is scoped despite known tool bypasses. |
| [test_e85_native_backend_conformance.py](../../tests/semantic_graph/test_e85_native_backend_conformance.py) and [gb03_native_backend_conformance.py](../../tools/gb03_native_backend_conformance.py) | Five-node/eight-occurrence adversarial graph; parallel edges including same labels; self-loop, cycle, isolated node, Unicode and nested values; full projection round-trip; seven query cases repeated twice; 14 exact reference-parity checks when a real library is installed | The fixture and parity checks do not prove query-time native local adjacency or guard against common-mode semantic errors. Optional-library skips remain skips; fake libraries do not count as native conformance. |
| [test_e83_multi_backend_traversal.py](../../tests/semantic_graph/test_e83_multi_backend_traversal.py) | Exercises service selection, fake module API behavior, sidecar/projection corruption rejection, explicit selection failure and real-library tests when installed | The fake adapters are contract doubles, not native libraries. A test currently asserts `semantic_traversal=True` for every registered adapter; M1 must replace that premature capability assertion with explicit conformance states. |
| [test_ae32b_backend_runtime.py](../../tests/semantic_audit/test_ae32b_backend_runtime.py) | Verifies trusted backend selection, observed queries and counters for NetworkX/SciPy; checks no silent model selection and runtime side-effect declarations | Query counters prove that the traversal engine was attempted; they do not prove which native data-structure APIs were called or whether the query enumerated the full graph. |
| [test_ae32b_evidence_tools.py](../../tests/semantic_audit/test_ae32b_evidence_tools.py), [test_ae32b_impact_dependency_tools.py](../../tests/semantic_audit/test_ae32b_impact_dependency_tools.py) | Exercises graph_neighbors, graph_path, related tests, static execution context and workflow context behavior; checks bounds, provenance, source hashes and static-only qualification | The context/workflow tests validate result semantics, not whether the selected backend served those operations. Current source confirms that those two tools still use their own canonical-graph walks. |
| [test_ae32c_patch2_graph_workflow_fidelity.py](../../tests/semantic_audit/test_ae32c_patch2_graph_workflow_fidelity.py) | Tests workflow command parsing, unresolved working directories, source-root/module resolution, type-checking-only import classification, related-test matching and traversal budget reporting | Good static semantics tests, but they do not cover backend routing or native adjacency. |
| [test_ae32c_graph_utilization.py](../../tests/semantic_audit/test_ae32c_graph_utilization.py), [test_ae32c_graph_pilot.py](../../tests/semantic_audit/test_ae32c_graph_pilot.py) | Measures graph-derived tool use, source follow-through, hash matching, claim linkage, matched control/ablation and cost/resource observations | These assess tool-use and evidence follow-through. They are not a substitute for deterministic adapter conformance, and they must keep model-requested calls separate from orchestrator prefetch. |

### 9.7 M0 tool-routing traceability

The current source and tests support the following more precise routing map:

| Evidence tool | Current behavior | M0/M2 assessment |
|---|---|---|
| `graph_neighbors` | Builds a `GraphQuery` and calls `_query_graph` | Routed through `SemanticGraphAnalysisService` and selected traversal engine |
| dependency/dependent and impact variants of `graph_neighbors` | Build dependency/impact `GraphQuery` instances and call `_query_graph` | Routed through selected traversal engine; verify each direction/relation/bounds combination in repository tests |
| `graph_path` | Builds a path `GraphQuery` and calls `_query_graph` | Routed through selected traversal engine |
| `find_related_tests` | Graph-backed `TESTS` queries use `_query_graph`; it also scans indexed source text for references | Hybrid tool: only its graph-query portion is backend-routed. Report graph and lexical/text-reference evidence separately |
| `trace_execution_context` | Builds its own import-edge adjacency, excludes `type_checking_only`, performs bounded context BFS | Not routed through selected traversal engine; retain its special filtering and provenance while migrating |
| `find_workflow_context` | Builds import/package-entrypoint/invocation adjacency and performs its own bounded path search | Not routed through selected traversal engine; retain workflow-specific semantics while migrating |

M2 should not simply replace these private walks with a generic neighbor call. It must preserve the domain-specific behavior: for execution context, exclusion of type-checking-only imports, source-line provenance, caller/dependency orientation, truncation and entrypoint derivation; for workflow context, `IMPORTS`, `PACKAGE_ENTRYPOINT` and `INVOKES` relationship handling, active-workflow scope, dynamic working-directory exclusions and bounded import-path search. Tests in `test_ae32b_evidence_tools.py` and `test_ae32c_patch2_graph_workflow_fidelity.py` supply valuable expected behavior for that migration.

### 9.8 Decision-record inventory findings

The current `docs/decisions/` directory contains **83 direct files**. Its filename inventory has ten reused ADR identifiers, with two distinct files for each identifier:

- ADR-035: graph-visualization boundary / verification boundary;
- ADR-036: evidence state machine / semantic verification boundary;
- ADR-037: candidate-knowledge isolation / evidence-state and verification decision;
- ADR-038: candidate-knowledge isolation / verification receipts;
- ADR-039: semantic-context versioning / verification receipts as immutable artifacts;
- ADR-044: impact-aware invalidation / NetworkX query runtime integration;
- ADR-045: append-only audit-memory ledger / unified native graph-adapter traversal;
- ADR-046: evidence-bound graph-impact analysis / impact propagation model;
- ADR-047: SciPy side-channel parity / incremental reverification boundary;
- ADR-048: audit-memory query model / native graph-backend conformance.

Additional anomalies:
- `ADR-016-backend-execution-context.md` contains one newline byte and no decision content.
- `ADR-079-bounded-multi-source-impact-and-dependency-cycles.md` has the heading `ADR-049` inside its body, while the filename and surrounding sequence identify it as ADR-079.

These findings do not establish which record should be canonical, superseded, or renumbered. M0 must compare dates, status, referenced implementation commits, inbound/outbound cross-references and decision scope before proposing a registry or correction. No ADR has been renamed or altered in this work.

### 9.9 M0 status

**M0 is now closed as a source-to-test traceability baseline.** The close-out is pinned to Stage1 commit `1ed0471832b660e8c29a946e4655e1ed981106bf`, with exact-commit G9.42 validation run `44885166907`. The close-out report records the adapter/tool trace, test-to-contract matrix, workflow/artifact chain, backend environments, ADR anomaly classification, and unresolved technical decisions:

[AE-32C M0 — Architecture Baseline and Traceability Close-out](AE-32C-M0-Closure-and-Traceability.md).

M0 closure does not imply that every backend has native query conformance. The outstanding adapter protocol, independent semantic tests, lifecycle/fault injection, and backend-specific native adjacency work are assigned to M1 and later backend milestones. The close-out report is the authoritative M0 snapshot; earlier findings in Sections 8–9 remain historical source observations and are interpreted through that report.

## 10. Immediate next work

Proceed with **M1**. M0's source-to-test traceability baseline is closed and recorded in [AE-32C M0 — Architecture Baseline and Traceability Close-out](AE-32C-M0-Closure-and-Traceability.md).

The M1 specification and implementation record are in [AE-32C M1 — Native Graph Adapter Protocol and Conformance Contract](AE-32C-M1-Adapter-Protocol-and-Conformance-Contract.md). The typed adapter interface, NetworkX local adjacency, and `BOTH` self-loop correction are committed; exact-commit tests have not been run, so M1 is not accepted or closed. It defines exact edge-occurrence adjacency, direction/self-loop semantics, capability/acceptance states, observational telemetry, and structural/behavioral/interaction/fault-injection tests.

Next:
1. Review the committed typed protocol and NetworkX implementation, especially occurrence identity and the `BOTH` self-loop rule.
2. Run the new `test_m1_adapter_protocol_networkx.py` plus E.8.2/E.8.8 anti-full-scan and repository tests on the exact Stage1 commit.
3. The E.8.5/E.8.8 workflow now runs the M1 protocol tests in its NetworkX job. Run it on this exact branch head; inspect NetworkX results separately from the known not-yet-implemented optional-backend adjacency gates.
4. Fix any failures and complete the remaining M1 lifecycle/fault-injection and reusable conformance gates.
5. Only after real NetworkX structural, behavioral and native-interaction evidence passes, extend the contract to SciPy, igraph, graph-tool and SNAP individually.

Do not begin E.8.8.3/SciPy native adjacency before the M1 contract and its NetworkX proof are accepted. No live provider test should compensate for missing deterministic conformance.

## 11. Change and evidence discipline

- All repository writes for this work target `stage1/section-uuids` explicitly.
- Do not create another branch or modify `main`.
- Do not rewrite history, force-push, or change the branch base.
- Keep implementation, test, documentation and CI changes traceable to a milestone.
- Run tests on the exact commit being reported; distinguish not-run, skipped, failed and passed.
- Record package versions, Python/platform details, commit SHA, workflow/run ID and artifact hashes where relevant.
- Keep Graphify as a discovery/indexing aid; source code, executable tests and runtime instrumentation remain the evidence authorities.

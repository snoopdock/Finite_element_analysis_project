# AE-32C — Graph Backend Compatibility and Utilization Roadmap

**Status:** M0–M6 accepted for their recorded historical exact Stage1 snapshots; later SNAP adapter timeout/cleanup work is validated for its declared E.8.5/E.8.8 scope at Stage1 source `51d025fd328b00a59988a05fe72d9092262434f5` in run `45395352748`, without extending historical M6 G9.42 acceptance. M7.1 five-backend smoke validation passed; M7.2 bounded traversal campaign accepted; M7.3 detached dossier verified and accepted for its stated scope. M7.4 expanded seeded-topology task acceptance passed across all five backend environments; the complete E.8.5/E.8.8 matrix and aggregate summary passed. Exact-source G9.42 passed against Stage1 SHA `d66f10b5c8af74b33a661c2453da3aca9982d565` in run `45400741779`; formal task/backend suitability verdicts remain pending. Production approval remains false  
**Target branch:** `stage1/section-uuids` only  
**Initial baseline reviewed:** `5a881c57cafc9ff17c3e01d3e1401ea9daf49225` — `AE-32C E.8.8.1`  
**Current M0 close-out snapshot:** `1ed0471832b660e8c29a946e4655e1ed981106bf` — `E.8.8.2`; G9.42 run `44885166907`  
**M1 accepted implementation snapshot:** `fb3f26e0600c5abe894fb54c9b0cecefed2476f2` — typed protocol, NetworkX native adjacency, `BOTH` self-loop correction and conformance states; validated by G9.42 run `44892453883`  
**M1 validation record:** [AE-32C M1 NetworkX Validation Record](AE-32C-M1-NetworkX-Validation-Record.md) — exact source SHA, 18 focused protocol tests passed, E.8.5/E.8.8 test gates passed, skips and artifact digests recorded  
**M2 validation record:** [AE-32C M2 NetworkX Context Routing Validation](AE-32C-M2-NetworkX-Context-Routing-Validation.md) — G9.42 run `44894696688`, exact source SHA `9dd02f7f98e0ad25d2225c638ed14bad4bd5d4e6`, all three context operations verified, evidence/provenance catalog passed  
**M2 implementation snapshot:** `9dd02f7f98e0ad25d2225c638ed14bad4bd5d4e6` — backend-neutral `GraphQuery` routing for repository context tools; validated by G9.42 run `44894696688` (672 targeted passed, 6 skipped; 3,603 regression passed, 14 skipped; evidence and provenance verified)  
**M3 implementation snapshot:** SciPy CSR outgoing and CSC incoming local edge-occurrence access; exact occurrence side-channel joins; full projection audit isolated to construction; accepted by G9.42 run `44898320570` against Stage1 SHA `c40a258f627a1678036521e2474fccdd5537e46a`  
**M3 implementation and validation record:** [AE-32C M3 SciPy Native Sparse Adjacency](AE-32C-M3-SciPy-Native-Sparse-Adjacency.md) — G9.42 run `44898320570`: 677 targeted passed, 6 skipped; 3,608 regression passed, 14 skipped; evidence and provenance verified  
**M4 accepted snapshot:** `c6d4fda93897a3b7022d28cba177fc5c453940b3` — G9.42 run `44901309538`, python-igraph 1.0.0; 682/686 targeted passed (4 skipped), 3,613/3,625 regression passed (12 skipped), 53 validation-engine tests passed; real igraph query, native conformance, repository context routing, evidence integrity, immutable bundle and provenance catalog all passed. Report SHA-256 `27e6714ca1a8160cb4c29078f187a1a2d071ee3e0b72a4b3bdccb1a866aec784`; bundle SHA-256 `aabd4edc501bb2cdec425dfa3f769a3b09467172d1d361736b497293b8226d19`  
**M4 implementation and acceptance record:** [AE-32C M4 python-igraph Native Adjacency](AE-32C-M4-python-igraph-Native-Adjacency.md) — exact-commit acceptance evidence for run `44901309538`; earlier failure reviews `44899514712` and `44900752438` retain the test-double diagnosis and correction history.
**M5 implementation snapshot:** graph-tool native per-vertex `out_edges()`/`in_edges()` traversal, explicit graph-tool edge-index to semantic-occurrence mapping, BOTH self-loop deduplication, payload verification, cached projection counts and native telemetry; real-library and repository gates added; implementation commit sequence begins `b91f439a79fff9b8c4b09aa6e0a16e0abf8b5dee` and latest recorded implementation commit `137b74bcb5f2908c8379e3ec72584a260492cd7e`; G9.42 plus dedicated conda-forge E.8.5/E.8.8 validation passed at exact Stage1 SHA `9adc99b9511d0281b18be76d60865dcf13bb16b0` (runs `44904263386` and `44905580330`); production approval remains false  
**M5 implementation record:** [AE-32C M5 graph-tool Native Adjacency](AE-32C-M5-graph-tool-Native-Adjacency.md) — API rationale, projection identity contract, local traversal, property-map limitations, tests, real-library workflow and exact-commit acceptance gates. The dedicated graph-tool job uses the conda-forge `graph-tool-base` package and reports its installed version.

**Scope:** Semantic graph adapters, native-library compatibility, traversal behavior, graph-tool and SNAP worker routing, repository-backed conformance and later runtime utilization  
**Change policy:** No branch creation or history rewriting. Application source, tests and milestone documentation are changed only on `stage1/section-uuids`. `main` may receive only narrowly scoped E85 workflow-controller/validator updates needed to validate Stage1; no application source changes or backend promotion occur on `main`.

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

### M2 — Complete NetworkX-backed routing for repository graph tools

**Purpose:** finish the strongest adapter first and establish a reference-quality integration pattern. This milestone concerns routing the repository's graph-derived tools through the selected backend; it does not mean the separate graph-tool native library is accepted (that remains M5).

Work:
- verify E.8.8.1 native `succ`/`pred` access and its tests at the exact baseline;
- prove occurrence-level parity, self-loop handling, deterministic ordering and defensive-copy behavior;
- route `trace_execution_context` and `find_workflow_context` through backend-independent `GraphQuery` operations;
- preserve type-checking import exclusions, bounds, line provenance, evidence shape and error behavior;
- expand repository conformance so each in-scope graph tool is checked for backend query deltas.

**Exit:** NetworkX passes all structural, behavioral, interaction and repository gates; `trace_execution_context` and `find_workflow_context` use backend-neutral graph queries with preserved domain semantics; no graph-derived tool silently bypasses the selected backend.

### M3 — SciPy native sparse adjacency

**Purpose:** use the sparse representation for actual query access.

Work:
- CSR row-based outgoing adjacency;
- CSC column-based incoming adjacency, or a measured and justified alternative;
- exact pair-to-occurrence side-channel joins for parallel edges and same-label duplicate occurrences;
- matrix structure and side-channel consistency checks;
- tests that forbid full edge readback during query execution;
- repository-backed parity and bounded access tests.

**Implementation now present on Stage1:**
- `SciPyAdapter` constructs a CSR connectivity/multiplicity matrix and a CSC incoming index once.
- Query adjacency reads only the selected CSR row, CSC column, or both; exact semantic occurrences, relation labels, attributes and metadata are joined from the side channels.
- `BOTH` deduplicates by occurrence ID, so a self-loop is returned once.
- The generic native traversal engine performs complete node/edge projection validation at construction, then skips repeated full readback for SciPy queries and obtains candidates through the SciPy adapter's local adjacency method.
- Runtime reporting uses cached projection counts and adjacency counters; it does not enumerate the full sparse graph.
- Tests were added for outgoing/incoming parity, parallel occurrences, self-loop union semantics, bounded reached-node access, query-time full-enumeration prohibition and repository context-tool routing.

**Exit:** SciPy passes the same acceptance gates as NetworkX, with native sparse access demonstrated by instrumentation. Implementation is not acceptance: exact-commit G9.42 evidence remains required.

### M4 — python-igraph native adjacency

**Status:** Native incident-edge implementation committed; exact-commit G9.42 validation pending.

**Purpose:** use native incident-edge indexes rather than full edge enumeration.

Implemented on Stage1:
- `Graph.incident(vertex_id, mode="out"|"in")` supplies native edge IDs;
- edge IDs are checked against canonical semantic occurrence IDs and full payloads;
- `BOTH` unions IDs, so self-loops are returned once and parallel edges remain distinct;
- traversal queries use native local adjacency after a one-time projection audit;
- projection counts are cached and runtime reports expose `igraph_incident_edge_ids` without full enumeration;
- fake-API structural/behavioral tests and registry-state assertions are added.

Validation still required:
- run G9.42 on the latest Stage1 head (the graph-core optional dependency group now includes python-igraph);
- ensure the real python-igraph test executes (not skips) and record the installed version;
- verify repository context-tool routing, native counters, source follow-through, full regression, evidence integrity and provenance catalog.

**Exit:** real python-igraph occurrence-level native adjacency and all shared acceptance gates pass. Fake-module tests alone are not acceptance.

### M5 — graph-tool native adjacency

**Status:** IN PROGRESS — implementation and fake/real-library/repository conformance work started after M4 acceptance.

**Purpose:** qualify graph-tool's native vertex/edge iteration and property-map model.

**Implementation now present on Stage1:**
- `GraphToolAdapter` constructs a directed graph-tool multigraph with vertex/edge property maps for semantic IDs, relation labels, attributes, metadata and occurrence IDs.
- Native edge indices are explicitly mapped to canonical semantic occurrence IDs; the implementation does not assume endpoint pairs or contiguous edge indices identify an occurrence.
- Per-vertex `out_edges()` and `in_edges()` supply local native candidates. `BOTH` unions by occurrence ID, so self-loops are emitted once and parallel edges remain distinct.
- Query-time endpoint, relation, attribute and metadata checks fail closed against the immutable projection; deterministic reference parity remains enabled.
- Full projection validation is performed once during construction. Query and runtime reporting use cached projection counts and graph-tool local iterators, with native adjacency and occurrence-read telemetry.
- Fake API tests, conditional real-library tests, native mutation tests and repository-backed context-tool conformance tests have been added.
- The dedicated conda-forge E.8.5/E.8.8 workflow now runs graph-tool adapter tests, synthetic native conformance and repository-backed context/source conformance.


**G9.42 validation attempt — run 44902653878:**
- The dispatcher was launched from `main`, but it checked out and validated `stage1/section-uuids` at exact source SHA `e979b17b081d5e0a3cf120b184c7016de6dfd3e1`. No source changes were made to `main`.
- Targeted suite: 689 tests, 684 passed, 5 skipped, 0 failed. Full regression: 3,628 tests, 3,612 passed, 13 skipped, 3 failed.
- Two failures came from a legacy graph-tool fake that lacked the `edge_index` property map; one was a stale M1 registry assertion that still expected graph-tool to be unimplemented.
- Corrections are committed to Stage1: `80f72b680b5f9b5e9bb15c1cf739cdd7d39cccd1` adds the missing fake edge-index mapping; `7becea4463b9276cbcdd49ad83f12a65d82806b7` asserts graph-tool `implemented_unvalidated` separately from SNAP `not_implemented`. The M5 fake was also strengthened in `beb4b80b00361aa882c00d97707090e2c0b651a6` to exercise non-contiguous native edge indices.
- Evidence integrity and immutable bundle publication passed. Provenance catalog build/verification correctly failed closed because regression failed. See [M5 G9.42 failure review](AE-32C-M5-G9.42-Validation-Failure-44902653878.md).
- At the time of this failure review, corrections were not yet validated. This pending status is superseded by the exact-commit G9.42 and dedicated graph-tool acceptance recorded in Section 12.

**Remaining validation work:**
- execute the dedicated conda-forge E.8.5/E.8.8 workflow against the exact latest Stage1 SHA and record graph-tool version;
- resolve any real-library incompatibilities without weakening occurrence identity, payload validation or bounded local adjacency;
- run G9.42 on that same exact Stage1 SHA and verify complete regression, evidence integrity, immutable bundle and provenance catalog;
- accept only when both reports bind to the same source commit and all repository context operations show native graph-tool execution.

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

**M1 is accepted for the NetworkX adapter contract and its tested repository-backed path.** The exact-commit evidence is recorded in [AE-32C M1 NetworkX Validation Record](AE-32C-M1-NetworkX-Validation-Record.md). G9.42 run `44892453883` checked out source SHA `fb3f26e0600c5abe894fb54c9b0cecefed2476f2`; all 18 focused M1 tests passed in regression, and the targeted E.8.5/E.8.8 modules passed. This acceptance does not extend to other native backends.

**M2 is accepted for the tested NetworkX-backed repository context path.** The implementation and validation-driven correction are documented in [AE-32C M2 — Context and Workflow Tool Backend Routing](AE-32C-M2-Context-Tool-Backend-Routing.md) and [M2 Validation Failure Review](AE-32C-M2-Validation-Failure-44893673258.md). G9.42 run `44894696688` checked out Stage1 source SHA `9dd02f7f98e0ad25d2225c638ed14bad4bd5d4e6`; targeted and full regression suites passed, evidence integrity verification passed, and the provenance catalog was published and verified. M2 acceptance remains limited to the tested NetworkX path.

The second G9.42 run, [44896382956](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44896382956), checked Stage1 SHA `60192a96dafef2e8f1381719950578d061114c2f`. Its only failure was a stale NetworkX context execution-mode expectation in `test_e88_networkx_repository_backend.py`; 676 targeted tests and 3,607 regression tests passed, with 6 and 14 skips respectively. The assertion now matches the runtime's established `networkx_successor_predecessor_adjacency` label. See [G9.42 Validation Failure Review — run 44896382956](AE-32C-G9.42-Validation-Failure-44896382956.md). This correction has not yet been validated.

**M3 is implemented but remains unvalidated.** The first G9.42 run, [44895368283](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44895368283), tested Stage1 SHA `78ece9ccdab4b4597930ba315d4c019175089119`. It reported 674 passed, 6 skipped and 2 failed in the targeted suite, and 3,604 passed, 14 skipped and 3 failed in full regression. The failures exposed (1) reference traversal string/enum normalization for BOTH self-loops, (2) missing per-query SciPy native-adjacency metrics in analysis result metadata, and (3) a stale M1 registry assertion. Technical review also found hard-coded NetworkX execution labels in the repository conformance report, which would mislabel SciPy context execution. The analysis and correction record is [M3 G9.42 Validation Failure Review](AE-32C-M3-Validation-Failure-44895368283.md); the M3 implementation record is [M3 SciPy Native Sparse Adjacency](AE-32C-M3-SciPy-Native-Sparse-Adjacency.md).

Corrective commits normalize traversal directions in the reference engine, expose per-walk SciPy CSR/CSC query counters, report the actual backend execution mode for all context operations, and update the affected tests. These changes are committed but have not been run by the implementer.

Next:
1. Run G9.42 against the latest `stage1/section-uuids` head.
2. Verify the reference and SciPy BOTH/self-loop test passes with one self-loop occurrence.
3. Verify direct trace, nested workflow context and direct workflow context each report positive SciPy native-adjacency lookups and occurrence reads, with `scipy_csr_csc_adjacency` as the execution mode.
4. Confirm the stale M1 registry expectation is corrected, targeted and full regression pass, and evidence integrity plus provenance catalog verification complete successfully.
5. Close M3 only after exact-commit evidence passes. Do not begin M4 (igraph) before SciPy acceptance.

The dedicated E.8.5/E.8.8 workflow was not separately dispatched for M1; the equivalent M1 and repository-runner assertions passed under G9.42. M2 acceptance does not extend to SciPy, igraph, graph-tool or SNAP. No live provider test substitutes for deterministic adapter conformance.

## 12. Latest M5 validation and SNAP workflow correction

The M5 acceptance gates are met for the tested graph-tool-base 3.9 / CPython 3.11.18 environment. G9.42 run `44904263386` and dedicated E.8.5/E.8.8 run `44905580330` both tested exact Stage1 SHA `9adc99b9511d0281b18be76d60865dcf13bb16b0`. G9.42 passed the validation engine (53), targeted suite (684 passed, 5 skipped), regression suite (3,615 passed, 13 skipped), evidence integrity, immutable bundle publication/verification and provenance catalog verification. The dedicated workflow ran four real graph-tool adapter tests; synthetic E.8.5 and repository-backed E.8.8 reports both passed. The repository report recorded 45 native adjacency lookups, 86 native edge occurrences read, zero failed queries/parity checks, and `graph_tool_vertex_edge_iterators` for the context operations. M5 acceptance is scoped to this environment and repository path; `production_approval` remains false. See [M5 implementation and validation record](AE-32C-M5-graph-tool-Native-Adjacency.md).

The same dedicated workflow failed overall only because the SNAP compatibility job requested CPython 3.9.19 on Ubuntu 26.04, where `setup-python` could not provision that interpreter. SNAP install and smoke did not execute. The correction pins that isolated job to Ubuntu 24.04, requests CPython 3.9 by minor version, installs the pinned `snap-stanford==6.0.0` binary wheel only, and records step outcomes in its artifact. The correction is not yet validated by a subsequent workflow run. See [run 44905580330 failure review](AE-32C-E85-Validation-Failure-44905580330.md).

**Next:** re-run the dedicated E.8.5/E.8.8 workflow against the updated Stage1 head. Verify the SNAP compatibility artifact reports CPython 3.9, successful binary-wheel installation and `status=passed` for the TNEANet smoke. This smoke is only a worker-runtime compatibility check; SNAP adapter implementation and repository-level acceptance remain unimplemented.

## 11. Change and evidence discipline

- Application implementation, tests and documentation target `stage1/section-uuids` explicitly.
- `main` is limited to the E85 workflow controller/definition validator; no application implementation changes are made there.
- Do not rewrite history, force-push, or change the branch base.
- Keep implementation, test, documentation and CI changes traceable to a milestone.
- Run tests on the exact commit being reported; distinguish not-run, skipped, failed and passed.
- Record package versions, Python/platform details, commit SHA, workflow/run ID and artifact hashes where relevant.
- Keep Graphify as a discovery/indexing aid; source code, executable tests and runtime instrumentation remain the evidence authorities.


## 13. Wrong-branch manual dispatch — run 44907031239

Run [44907031239](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44907031239) was dispatched from `main` at controller/source SHA `c54919c39bf656ef4562320008f6aa7df8b2e844`, not from Stage1. Logs confirm the old main workflow: SNAP requested CPython 3.9.19 on Ubuntu 26.04; NetworkX could not find the Stage1 M1 test; SciPy/igraph could not find the E.8.5 runner; graph-tool could not find its conda environment file. These are wrong-branch content failures and do not invalidate the Stage1 adapter implementation or its earlier exact-source graph-tool acceptance.

To avoid dependence on the Actions mobile branch selector, the workflow controller on `main` now exposes a constrained `source_ref` workflow-dispatch input and passes it explicitly to every checkout. It is intended to be dispatched from main with `source_ref=stage1/section-uuids`; each job logs the actual checked-out source SHA. See [run 44907031239 analysis](AE-32C-E85-Validation-Failure-44907031239.md). The next run must verify the checked-out Stage1 SHA before any job result is used as conformance evidence.


## 14. E.8.8 expansion and M6 isolated SNAP worker implementation — 2026-11-21

### 14.1 E.8.8 scope expansion

The manual E85 workflow controller on `main` and the branch-local Stage1 workflow now run the repository-backed E.8.8 gate for all executable backend jobs:

- NetworkX, SciPy and igraph in the Python 3.11 pip matrix;
- graph-tool in its dedicated conda-forge environment;
- SNAP through a restricted CPython 3.9 worker with a Python 3.11 orchestrator.

This removes the earlier deliberate deferral of SciPy and igraph repository-level parity. In run [44914650206](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44914650206), at Stage1 SHA `7771d637cd613bf5cfc8c847108cd0c6eb28c98f`, NetworkX, SciPy, igraph and graph-tool each passed both E.8.5 and E.8.8. The graph-tool E.8.8 step also passed. The SNAP Docker image built successfully and the worker-adapter protocol test passed, but SNAP E.8.5 failed before native graph construction; SNAP E.8.8 was therefore skipped. The workflow's overall failure is correctly retained.

### 14.2 SNAP failure diagnosis, correction and successful real-worker validation

Two defects were found and corrected during the first real worker attempts:

1. The worker validator initially required a raw 64-character SHA-256 string, while the canonical graph identity function returns `graph:` followed by 32 lowercase hexadecimal characters. Commit `9f0125738759be4bb80026d9aa86d59a01e915b8` corrected the format check.
2. The next attempt passed fingerprint validation but could not load SNAP because `libgomp.so.1` was missing from the slim Python 3.9 image. Commit `97f78060923a9ab7daea8ed4b48971c0314b3616` added Debian `libgomp1` to the worker image.

The worker then required and probed the actual SNAP Python binding for TNEANet `GetOutEId` and `GetInEId` accessors. The installed SNAP 6.0.0 / CPython 3.9.25 runtime exposed both, and the full run [44914959176](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44914959176) completed successfully at Stage1 SHA `425c0f7378bfe190da81b10b0f6e0b22c3df4f41`.

Results from that run:

- NetworkX: E.8.5 and E.8.8 passed.
- SciPy: E.8.5 and E.8.8 passed.
- igraph: E.8.5 and E.8.8 passed.
- graph-tool: E.8.5 and E.8.8 passed.
- SNAP 6.0 isolated worker: E.8.5 and E.8.8 passed.

For SNAP, E.8.5 verified 14/14 repeated queries with zero parity failures, 34 native adjacency lookups and 96 native edge occurrences read. E.8.8 verified 43/43 repository queries with zero parity failures, 45 native adjacency lookups and 86 native edge occurrences read. The graph-to-source follow-through verified two source reads against SHA-256 hashes. The final worker image ID was `sha256:9701ec285db9ed7d41415ce7b6950f7ae27ce54ea99ea4469d0e0f524d007ee1`.

The E.8.5/E.8.8 runner reports and workflow now also stamp the actual checked-out Stage1 source SHA, workflow run ID and attempt. A provenance-stamped run is triggered on the current Stage1 head by the workflow/documentation commit. G9.42 exact-commit validation remains the final milestone gate.

### 14.3 M6 implementation record

The M6 worker implementation consists of:

- `tools/snap_worker.py`: Python 3.9-compatible, versioned JSON-lines worker; strict operation schemas; one-time TNEANet projection audit; native outgoing/incoming edge-ID queries; explicit semantic occurrence mapping; bounded input, graph and adjacency sizes.
- `audit_engine/semantic_audit/graph/backend/snap_worker_adapter.py`: Python 3.11 proxy that launches the worker container, minimizes the child environment, binds requests to the canonical graph fingerprint, validates responses and maps native edge records back to canonical occurrences.
- `.github/snap-worker/Dockerfile`: pinned SNAP distribution and worker-only image contents; the repository source is not copied into the runtime image.
- `tests/semantic_graph/test_snap_worker_adapter.py`: protocol and container-launch contract test using a fake process. This is a unit test, not SNAP native acceptance.
- `tools/gb03_native_backend_conformance.py`: refuses to mark SNAP E.8.5 as passed unless the isolated worker adapter is active and native adjacency telemetry is observed.
- `tools/gb04_repository_backend_conformance.py`: includes worker image/runtime provenance in the E.8.8 report.

The worker container is launched with network disabled, a read-only root filesystem, no writable mounts, IPC disabled, no repository bind mount, dropped Linux capabilities, no-new-privileges, a non-root identity and explicit CPU/memory/PID limits. The Docker build itself needs network access to fetch its base image and the pinned binary wheel; the runtime worker container does not have network access. The Docker image ID is recorded in the workflow environment and worker evidence.

In run `44914959176`, SNAP E.8.5 completed 14/14 queries with zero parity failures, 34 native adjacency lookups and 96 edge occurrences read. SNAP E.8.8 completed 43/43 repository queries with zero parity failures, 45 native adjacency lookups and 86 edge occurrences read. The graph-to-source gate verified two SHA-256-bound reads. The worker reported CPython 3.9.25 / SNAP 6.0.0 and image ID `sha256:55b531951c9f7f70bc0414ce4a59059d6602df3ec15e17bf0732099bd602f593`.

SNAP's TNEANet native incident edge IDs are used through `GetOutEId` and `GetInEId`; each is resolved with `GetEI` and checked against a stored `semantic_occurrence` attribute. This preserves parallel edge occurrences and allows a bidirectional query to deduplicate a self-loop by native edge identity. Attributes are stored as canonical JSON strings, an explicit reversible representation transformation for JSON-compatible payloads.

See [AE-32C M6 SNAP Isolated Worker — Implementation and Acceptance](AE-32C-M6-SNAP-Isolated-Worker-Implementation-and-Acceptance.md) for the protocol, container policy, evidence schema, API references, limitations and acceptance gates.

### 14.4 Milestone state and next gates

| Milestone | Current state | Remaining acceptance requirement |
|---|---|---|
| M5 graph-tool | Previously accepted at exact SHA `9adc99b...`; E.8.5/E.8.8 passed again at final SHA `c7fe14c...` | Run G9.42 at exact SHA `c7fe14c52ded38eafbf3153137bf163efaa3f0e6` before closing current-head revalidation. |
| M6 SNAP | Real isolated worker E.8.5 and E.8.8 passed at SHA `425c0f7...` | Run G9.42 at exact SHA `c7fe14c52ded38eafbf3153137bf163efaa3f0e6` before recording M6 accepted. |
| M3 SciPy / M4 igraph | Their historical exact-SHA acceptance records remain valid; E.8.5/E.8.8 also passed together at SHA `425c0f7...` | No promotion; preserve `production_approval=false`. |

Do not infer final milestone closure from a successful Docker build or fake-process test alone. The real E.8.5/E.8.8 gates for all five backends are green on exact Stage1 SHA `c7fe14c52ded38eafbf3153137bf163efaa3f0e6`; the remaining closure gate is a successful G9.42 Manual Validation Dispatcher report for that same SHA. Do not change registry production approval.


## 15. M5/M6 closure and AE-32C M7 opening — 2026-11-21

### 15.1 Exact-commit M5/M6 closure

The Stage1 acceptance snapshot is `81eb77aff35afe297a596a91826e016048515c0f`.

- Full five-backend E.8.5/E.8.8 run [44917397347](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44917397347) passed on that exact SHA. NetworkX, SciPy, python-igraph, graph-tool and SNAP each passed 14/14 synthetic E.8.5 queries and 43/43 repository-backed E.8.8 queries, with zero query failures and zero parity failures. All ten reports carry the same source SHA, run ID and attempt.
- Exact-commit G9.42 run [44917571217](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44917571217) passed on the same exact SHA: 53 validation-engine tests, 690 targeted tests (5 skipped), 3,629 regression tests (13 skipped), evidence digest/checksum verification, immutable bundle publication/verification and independent provenance catalog verification.
- The detailed evidence and acceptance boundary are recorded in [M6 implementation and acceptance record](AE-32C-M6-SNAP-Isolated-Worker-Implementation-and-Acceptance.md).

**Decision:** M5 graph-tool and M6 SNAP are accepted for the tested Stage1 runtime, backend implementations and repository fixture. This is not production approval, a universal performance claim or a claim of live LLM diagnostic quality. Keep `production_approval=false`.

### 15.2 AE-32C M7 — Comparative backend performance and promotion policy

M7 is OPEN and is governed by a task-suitability objective, not a universal performance competition. The five graph libraries are computational options. The audit engine may use different libraries for different problem classes according to their algorithmic relevance, representation capabilities, semantic-preservation behavior, native APIs, integration constraints and operational costs.

The canonical `SemanticGraph` remains authoritative. A computational backend is a replaceable projection and must not own semantic identity, evidence or provenance. A backend may be appropriate for sparse numerical operations and not for rich multigraph evidence traversal, or vice versa. Such judgments require task-specific operation contracts and validation.

The M7 protocol and updated sequence are defined in [AE-32C M7 — Task Suitability and Operational Characterization](AE-32C-M7-Comparative-Backend-Performance-and-Promotion-Policy.md):

1. M7.0 baseline freeze and protocol — completed.
2. M7.1 five-backend native smoke and parameter-propagation gate — passed in run `44937517812`.
3. M7.2 deterministic workload families and bounded multi-seed per-backend campaign — initial implementation committed; exact-source validation and five-backend execution pending.
4. M7.3 independent campaign-artifact verification and descriptive dossier.
5. M7.4 task-specific suitability statements and explicit policy.

M7 timing is supporting operational evidence only. No universal winner, scalar backend score or automatic selector is part of this milestone. A future task-specific suitability statement must name the actual audit operation, graph shape, semantic invariants, native API, runtime/deployment constraints and evidence limitations. Keep `production_approval=false`.

### 15.3 M7.1 exact-source validation and five-backend smoke controller — 2026-11-21

The M7.1 implementation is validated by the exact-source five-backend manual run [44937517812](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44937517812). The workflow revision was `182d0009f1c759c46813e3a1cbbf34d22c247acb`; the requested Stage1 branch resolved to `342c9d55b1dc49ccf93759d0dce203723485ef17`. All eight workflow jobs passed. The workflow-definition lint and immutable source-resolution jobs passed, and all five backend jobs checked out the same resolved source SHA.

The dispatch used 15 measured repetitions and 5 warm-up calls per query. The source-resolution job, all five backend jobs and the final summary received those exact values. The workflow's JSON configuration assertions passed, and each report recorded 15/5 for all seven query scenarios. The five independent report verifiers returned `status=verified`; query result digests agreed across backends. This closes M7.1's smoke and input-propagation gate.

The backend jobs ran on separate hosted runner instances. Their timings are not a controlled cross-backend comparison and are not ranked. This run proves native-path execution and report integrity on the fixed E.8.5 fixture, not broad task suitability. See [run 44937517812](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44937517812).

### 15.4 M7.2 task-suitability workload campaign — initial implementation

M7.2 adds `tools/gb06_task_suitability_campaign.py` and `tests/semantic_graph/test_m72_task_suitability_campaign.py`. The campaign defines five deterministic workload families: sparse dependency, hub-heavy impact, parallel evidence multigraph, disconnected components and dense local neighborhoods. It supports 2–5 distinct ascending seeds, 3–15 measured repetitions and 0–5 warm-up calls.

For each backend, the campaign records separate workload/seed cases, canonical graph digests, five common bounded traversal queries, parity against the independent `GraphTraversalEngine`, native query mode, native adjacency counters, construction time, raw timings and environment/worker provenance. The verifier reconstructs every generated graph, regenerates the query manifest and expected reference outputs, checks sample counts and recomputes descriptive aggregates. It rejects altered workload/result/aggregate claims and authority escalation.

The first M7.2 scope is intentionally limited to bounded semantic traversal under varied graph shapes. It does not claim to qualify sparse numerical linear algebra, centrality, community detection, ontology reasoning or end-to-end evidence reconstruction. Those require distinct task contracts and workload oracles. The five libraries remain computational options; M7.2 does not calculate a global ranking or select a winner.

The new M7.2 test module has been added to `validation/profiles/G9.42.yaml`. The manual five-option campaign controller is committed on `main` at `64fa7e662ffa5359fe4430b9273aa4a1bf6691f5` as `.github/workflows/m7_2_manual_task_suitability_campaign.yml`. It resolves the requested source once and pins five separate backend jobs to the same SHA; graph-tool uses the existing conda-forge environment and SNAP uses the restricted worker. The workflow has an actionlint preflight but has not yet been dispatched. Current Stage1 implementation commits:
- `6d579da8e613274b41123eed64405859b07235a5` — campaign runner and deterministic workload generator.
- `d205f0b881312edf1b930d07cca66df152f22ac6` — initial campaign integrity and workload tests.
- `ffeb99b9dac2646f5da232510ab5553d6647db0a` — G9.42 profile inclusion.
- `0265f0548ee742f0533287978ec9b29889fec614` — M7 task-suitability protocol update.
- `9b3a67651d323601fd8763361ee28c58c843766f` and `e354d5e6023fd1d3a2e26c7312b3df10d47af339` — hardened workload descriptor and environment verification.
- `2638c9cda2acaf5b26b29c427f662f9c921a1176` — tests for environment and workload descriptor integrity.
- `ab942db734ea4e51492ff1c0c3e1a219ee821056` and `10c6be6014d05e7d6d2d36870a44d9ccab1fc949` — milestone/roadmap evidence updates.

The current Stage1 head after these documentation updates is `10c6be6014d05e7d6d2d36870a44d9ccab1fc949`.

**Next acceptance gates:** run G9.42 against the current Stage1 head; correct any failures before dispatching the five backend campaign reports. Then run each backend against the same Stage1 source SHA, seeds, workload family set, repetitions and warm-up settings; inspect all artifacts and verify each report independently. Environment differences must be disclosed, and measurements must not be ranked across unmatched runner environments. Keep `production_approval=false`.


## 16. AE-32C M7.2 campaign closure and M7.3 dossier implementation — 2026-11-21

M7.2 was executed against the exact Stage1 source SHA 1122916e8a56abec43cf3d42f8b2d252533e81c1. G9.42 run [44940231437](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44940231437) and the five-backend campaign run [44940960831](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44940960831) both succeeded. All five backend reports used the same two seeds and five workload families with the intentionally selected 15 repetitions and 5 warm-up calls per query. All graph and query-result digests matched across backends; native-path and preflight parity evidence was present. Azure and AWS runner strata are retained separately; no timing ranking is valid.

M7.3 implementation adds:
- tools/gb07_campaign_dossier.py for detached report, artifact metadata, provenance, workload/seed matrix, cross-backend graph/result digest, native-path, parity and aggregate checks;
- tests/semantic_graph/test_m73_campaign_dossier.py for adversarial dossier-integrity tests;
- a G9.42 profile entry for the M7.3 tests;
- the manual main controller .github/workflows/m7_3_detached_campaign_dossier.yml, updated through main controller commit bd5260926d468876dc58182e2c310237ffe9e5c9.

The verifier generates JSON and Markdown dossiers. It records the GitHub Actions artifact digest metadata and extracted report/log file hashes. It does not claim that an internal report hash authenticates its source, that historical timing samples can be re-executed, or that measurements from separate hosted runners are directly comparable.

**Current state:** M7.2 accepted for bounded semantic traversal. M7.3 is closed for its stated detached-artifact consistency scope: exact-source G9.42 run `44943859099` and manual detached-dossier run `44945256220` passed, and the generated dossier was inspected. M7.4 is unblocked. Its task-specific assessment contract is recorded in [AE-32C M7.4 Task-Specific Backend Suitability Assessment Contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md). No task/backend suitability verdict is issued yet. Preserve `production_approval=false`.


## 17. M7.3 closure and M7.4 assessment-contract freeze — 2026-11-21

M7.3 detached dossier verification completed successfully in [run 44945256220](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44945256220). Both workflow jobs passed: workflow-definition lint/actionlint and independent verification of the five detached backend artifacts. The verifier used controller revision `cafa0d1be5c09eb092c1bc2467b540f20acb22b9` and exact Stage1 verifier source revision `47eb1ae6777e1d34c445af219c96840797739f23`; the underlying M7.2 campaign was run `44940960831`, attempt 1, source SHA `1122916e8a56abec43cf3d42f8b2d252533e81c1`. The published dossier was inspected. M7.3 is accepted only as detached artifact/report/log provenance and internal-consistency verification; it does not re-execute historical timings or independently authenticate physical runners.

M7.4 begins with the contract in [AE-32C M7.4 Task-Specific Backend Suitability Assessment Contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md), committed on `stage1/section-uuids`. The contract inventories the four public graph-analysis query paths (STRUCTURAL, DEPENDENCY, PATH and IMPACT), defines the required evidence record and outcome vocabulary, and separates generic traversal evidence from higher-level operation acceptance. It identifies additional evidence needs for multi-source impact/cycle analysis, SciPy's semantic side channels, and SNAP worker identity/timeout/recovery. The initial contract commit is `4bc5718674e4b406face788bce513c4a17eaa56f`; selector-behavior clarification is recorded in follow-up commit `9af169f45798bbabe0c7ed7a3bce1f5067a61ab8`. The reviewed code baseline is `47eb1ae6777e1d34c445af219c96840797739f23`.

**M7.4 status:** assessment contract defined; implementation-level task/backend suitability assessments and verdicts remain pending. Do not infer suitability from M7.2 parity alone. Keep `production_approval=false`, do not rank libraries, and do not activate automatic backend selection.


## 18. M7.4 initial STRUCTURAL / DEPENDENCY / PATH task-level acceptance — 2026-11-24

The first M7.4 executable assessment tranche is committed at Stage1 source SHA `942b54f8948286b4727ca208fdfa553e019437b9` (parent `e6a985d44cc97521f730fc717f35fd4a0d9bf4cd`). It adds `tests/semantic_graph/test_m74_task_suitability_acceptance.py`, includes that test module in G9.42, and runs the selected-backend partition from each of the five existing native-backend CI environments.

The push-triggered [E.8.5 / E.8.8 native-backend workflow run 45381213888](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45381213888) checked out the exact commit above in all five jobs. The M7.4 test step reported 7 passed and 28 intentionally skipped in each environment (the skipped cases belong to the four non-selected backend partitions). Thus, 35 backend-specific task test executions passed across the five environments. The five native conformance jobs and aggregate summary also completed successfully.

The tested public service paths cover STRUCTURAL one-hop direction/relation behavior, parallel edge-occurrence evidence and self-loop behavior; DEPENDENCY direct/transitive traversal and bounded truncation; and PATH bounded path/evidence output and incomplete status under a step limit. The tests compare semantic outputs with the reference implementation, assert native query mode and nonzero native adjacency telemetry, verify per-query reference parity, and check that the canonical graph remains unchanged. This is synthetic task-level test evidence, not representative scale/workload coverage or a complete G1–G8 suitability dossier.

The SNAP job records Docker image ID `sha256:f94d166165f7676f031bb476a79b0c7e112ef65f0f9c4ef5027844891f1eb4b3` for this execution. This remedies the missing image-identity field for this particular run only. It does not implement a per-request response deadline or establish worker timeout/recovery behavior.

The detailed run record is [AE-32C M7.4 Initial Task Assessment Validation](AE-32C-M7.4-Initial-Task-Assessment-Validation.md). G9.42 was updated to include the new test file but was **not** dispatched in this run. STRUCTURAL, DEPENDENCY and PATH therefore have positive initial task-level evidence, not final backend suitability verdicts. IMPACT remains unassessed. The generic selector's implicit first-match behavior remains outside this change. Do not infer universal suitability, ranking, runtime promotion, or production approval; preserve `production_approval=false`.


## 19. M7.4 IMPACT acceptance follow-up — 2026-11-24

The initial M7.4 test suite now covers all four public query/analyzer tasks: STRUCTURAL, DEPENDENCY, PATH and IMPACT. The corrected test source is `ff6fe8226d6417b0832a17b8bed397217f72a303`; push-triggered [E.8.5 / E.8.8 workflow run 45382782600](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45382782600) checked out that exact revision in all five backend environments. Each backend's M7.4 step passed 11 tests and intentionally skipped 44 cases for the four unselected backend partitions. The five backend jobs and aggregate summary succeeded.

IMPACT-specific tests verify multi-source candidate merging and per-source attribution, deterministic source-order handling, one-hop ownership/evidence resolution, test/workflow/symbol candidates, cycle SCC evidence, bounded source budgets and explicit incomplete states, cycle-scan edge limits, and rejection of duplicate or over-25 source sets. The test helper also requires native traversal telemetry, parity verification for each traversal query and zero backend query errors. The canonical semantic graph is checked for mutation.

**Execution decomposition:** IMPACT's ownership and reverse-dependency walks run through the selected traversal backend. Its cycle analysis reads/sorts the canonical `SemanticGraph.edges` collection, applies the 50,000-edge guard, induces the impacted-node subgraph and computes SCCs with the analyzer's iterative Kosaraju implementation. It is not a native backend SCC operation. Any suitability statement must distinguish these sub-operations; it must not present the full IMPACT path as wholly backend-native.

The preceding test commit `b6b81b60753cf36334281f19c3ff64aea5abe7b9` exposed an over-broad expectation for a second-hop `MEMBER_OF` ownership edge. The correction at `ff6fe8226d6417b0832a17b8bed397217f72a303` aligned the expected evidence with the file-source analyzer's one-hop ownership walk. No runtime source change was made for this test correction. The corrected five-backend run then passed.

The SNAP worker image ID was recorded as `sha256:8aa923b1de4d7b2ca7301cb27556178e35e8c54cff433f0c5d653320637f089e`. Its per-request `stdout.readline()` deadline, timeout propagation and recovery are still open. G9.42 includes the M7.4 suite but was not run against this source. The detailed test and run record is [AE-32C M7.4 Initial Task Assessment Validation](AE-32C-M7.4-Initial-Task-Assessment-Validation.md).

**Current M7.4 status:** initial synthetic acceptance tests cover all 20 task/backend combinations; final G1–G8 task/backend records and formal verdicts remain pending. No ranking or automatic selection is introduced. Preserve `production_approval=false`.


## 20. M7 SNAP worker request-deadline and cleanup follow-up — 2026-11-24

The previously unbounded SNAP JSON-lines request has been bounded in the Stage1 adapter. The current implementation revision is `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86`.

The request deadline defaults to 120 seconds, is configured through `AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS`, and cannot exceed 600 seconds. The deadline covers both pipe write/flush and response read. Graceful close is limited to five seconds. Docker launch now records the exact container ID with `--cidfile`; timeout cleanup attempts `docker rm --force` with a two-second command timeout, then bounds termination/kill of the host Docker client, closes streams and removes the temporary state directory. The adapter does not attempt an automatic restart after timeout.

The adapter tests cover blocked writes, blocked reads, blocked close, invalid timeout configuration and the forced-removal command invocation/order. They use simulated process/Docker behavior rather than a live Docker daemon test.

Exact-source [E.8.5/E.8.8 run 45385374806](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45385374806) shows successful SNAP adapter protocol tests, M7.4 task acceptance and SNAP synthetic E.8.5. NetworkX, SciPy, igraph and graph-tool jobs succeeded. At the latest inspection, SNAP repository-backed E.8.8 was still in progress after approximately 35 minutes. No final SNAP report or artifact was available; the whole matrix remains pending rather than accepted.

The old M6 G9.42 acceptance is only for its recorded historical snapshot and cannot be reused for the new adapter code. The current G9.42 profile contains `test_snap_worker_adapter.py` and `test_m74_task_suitability_acceptance.py`, but G9.42 has not been dispatched against `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86`.

The next gates are: determine why SNAP E.8.8 is unusually long or allow its declared job timeout to produce a final result; add/execute a live Docker stalled-worker cleanup test; and perform exact-source G9.42 through the manual dispatcher. Do not issue final task/backend suitability verdicts, promote a backend or change `production_approval=false`.

## 21. Live SNAP Docker timeout cleanup — 2026-11-24

At exact Stage1 source `7a77b52c316c60ffb8f433af2bbd1b742f389972`, the new `tests/semantic_graph/test_snap_worker_docker_lifecycle.py` integration step passed. The live Docker lifecycle test `tests/semantic_graph/test_snap_worker_docker_lifecycle.py` passed. It built a disposable worker container that deliberately did not respond, observed the adapter request deadline, verified `docker rm --force` used the exact container ID captured by `--cidfile`, and confirmed that `docker inspect` could no longer find the container. This is direct live Docker evidence on the tested GitHub-hosted runner, not merely a mocked process test.

In exact-source workflow run `45391619634` at `7a77b52c316c60ffb8f433af2bbd1b742f389972`, the SNAP adapter protocol/restriction tests, live Docker timeout cleanup test, M7.4 task suite and synthetic E.8.5 all succeeded. NetworkX, SciPy, python-igraph and graph-tool jobs also succeeded. At the last inspection, SNAP repository-backed E.8.8 remained `in_progress` after approximately 12 minutes; no final SNAP repository report or artifact was available. Do not count the matrix as complete.

The four non-SNAP backend jobs passed. The SNAP adapter protocol, M7.4 task acceptance and synthetic E.8.5 steps passed as well. The E.8.8 repository-backed stage has not produced a final result and remains the active validation boundary.

The G9.42 profile now includes `tests/semantic_graph/test_snap_worker_adapter.py`, `tests/semantic_graph/test_snap_worker_docker_lifecycle.py`, and `tests/semantic_graph/test_m74_task_suitability_acceptance.py`. Exact-source G9.42 has not been dispatched. The default-branch manual dispatcher is `workflow_dispatch` only, and the available GitHub connection does not expose a workflow-dispatch action.

Next work: resolve or instrument SNAP E.8.8; add the prepared M7.2 seeded-topology task tests; and run exact-revision G9.42 through the manual dispatcher. No final suitability verdict, ranking, automatic selector or production approval is implied.


## 22. Expanded M7.4 task workloads and completed E.8.5/E.8.8 matrix — 2026-11-24

**Exact source:** `51d025fd328b00a59988a05fe72d9092262434f5`  
**Workflow:** [E.8.5/E.8.8 workflow run 45395352748](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45395352748)  
**Aggregate summary job:** `138450475726`

All five backend jobs reported **21 passed, 84 intentionally skipped** for `tests/semantic_graph/test_m74_task_suitability_acceptance.py`:

| Backend | Job ID | M7.4 test result |
|---|---:|---:|
| NetworkX | `138449745984` | 21 passed, 84 skipped |
| SciPy | `138449746035` | 21 passed, 84 skipped |
| python-igraph | `138449745936` | 21 passed, 84 skipped |
| graph-tool | `138449746042` | 21 passed, 84 skipped |
| SNAP isolated worker | `138449745692` | 21 passed, 84 skipped |

The 84 skips in each job are the four backend partitions not selected by that job. Across the five environments this is 105 passing backend-specific test executions and 420 expected skips; it is not 105 different test definitions.

The expanded tranche adds 10 parametrized topology cases per selected backend: five seeded M7.2 workload families and two fixed seeds (`20261101`, `20261102`). Each base topology is replicated three times as disjoint components, and each case executes STRUCTURAL, DEPENDENCY, PATH and two-source IMPACT analysis through the public service, compares with the reference service, checks native-mode/parity/adjacency telemetry, and verifies canonical-graph immutability.

| M7.2 topology family | Base graph | Three-replica assessment graph |
|---|---:|---:|
| `sparse_dependency` | 48 nodes / 96 edges | 144 nodes / 288 edge occurrences |
| `hub_impact` | 48 / 176 | 144 / 528 |
| `parallel_evidence` | 32 / 144 | 96 / 432 |
| `disconnected_components` | 64 / 128 | 192 / 384 |
| `dense_local_neighborhood` | 32 / 256 | 96 / 768 |

These are semantic/task-fit fixtures, not timing benchmarks. No backend is ranked and no global winner is inferred.

### 22.1 SNAP repository conformance and explicit worker closure

The preceding SNAP E.8.8 run `45391619634` reached the end of the semantic checks and emitted a passed report, but the process did not exit because the repository conformance runner left the backend adapter open. The correction added `RepositoryEvidenceTools.close()`, a `try/finally` wrapper in `tools/gb04_repository_backend_conformance.py`, and phase markers. The latest exact-source run logged both `closing_backend_resources` and `backend_resources_closed` before final JSON output, and the E.8.8 step succeeded.

The SNAP E.8.8 report completed with `status: passed` and source SHA `51d025fd328b00a59988a05fe72d9092262434f5`. It records 43 attempted/successful backend queries, 43 reference-parity verifications, zero query failures and zero parity failures; 45 native adjacency lookups and 86 native edge occurrences read. The repository fixture is complete: 26 nodes, 41 edge occurrences, 9 indexed files, graph fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`, and source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. The runner followed graph-surfaced paths to two source reads (`main.py` and `tests/checks.py`) and verified both SHA-256 values.

The per-operation context telemetry is also complete: trace context 7/7 parity-verified adjacency queries; workflow context 16/16; nested workflow context 16/16. The SNAP worker was CPython 3.9.25 / SNAP 6.0.0, image ID `sha256:a3ab78cf8512048adfc3570bff591772c1542dfb09226363142c6779934f59a5`, with the declared isolated container restrictions. E.8.8 used a 30-second worker request deadline.

SNAP's adapter protocol, live Docker timeout/forced-removal integration, repository backend teardown contract, M7.4 task suite and E.8.5 all passed. The entire five-backend E.8.5/E.8.8 workflow and aggregate summary succeeded.

### 22.2 Expanded test-oracle correction

The first expanded suite used IMPACT `max_depth=6`; the analyzer rejects values greater than 5. The failed tests therefore stopped at the common analyzer validation boundary. The fixture was corrected to depth 5 at `51d025fd328b00a59988a05fe72d9092262434f5`; no runtime algorithm was changed. The corrected test suite passed in all five backend environments.

### 22.3 Current acceptance boundary

This supplies substantially broader G5 synthetic task-workload evidence than the original five-node diagnostic fixture. It still does not establish performance superiority, production scale behavior, domain-specific claim-to-evidence completeness, or native backend SCC execution for IMPACT. Per-task/per-backend G1–G8 records and formal suitability outcomes remain pending. The updated G9.42 profile contains the adapter, live Docker, teardown and M7.4 tests, but exact-source G9.42 has not been dispatched. Preserve `production_approval=false`.


## 23. M7.4 preliminary 20-pair G1–G8 evidence ledger — 2026-11-24

The next M7.4 decision artifact is [AE-32C M7.4 Preliminary Task/Backend Evidence Matrix](AE-32C-M7.4-Preliminary-Task-Backend-Evidence-Matrix.md). It contains one preliminary record for every combination of the four public task/analyzer paths and the five computation backends, binds the positive acceptance evidence to exact source 51d025fd328b00a59988a05fe72d9092262434f5 and run 45395352748, lists exact repository-run library versions/native query modes, and marks G1–G8 gate states.

The ledger does not turn 105 passing backend-specific test executions into 20 suitability approvals. All 20 outcomes remain Insufficient evidence: G5 seeded topologies still require representative audit-domain workloads; G4 needs broader stale/corrupt projection and lifecycle tests; G6 needs full operational/resource envelopes; and G7 needs a detached verifier pass for this exact evidence set. PATH domain-specific claim-to-evidence behavior remains unqualified, and IMPACT SCC cycle analysis remains canonical-graph based rather than native backend SCC execution.

Exact-source G9.42 was subsequently dispatched and passed against this Stage1 snapshot in run `45400741779`; see Section 24. The separate G7 verification of the five-backend E.8.5/E.8.8 artifact set and the other task-suitability gates remain open. Preserve production_approval=false; no global winner or automatic backend selection is authorized.

## 24. Exact-source G9.42 manual validation — 2026-11-24

Manual Validation Dispatcher run [45400741779](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45400741779) passed with branch `stage1/section-uuids`, profile `G9.42` and regression mode `profile`. The exact tested source SHA was `d66f10b5c8af74b33a661c2453da3aca9982d565`; the run's `main` SHA `ee4e4b769221d331b1d2726301349cd0c217ab03` supplied the central validation engine and dispatcher. The report binds these separately.

Results: 53 validation-engine tests passed; 846 targeted tests (799 passed, 47 skipped); 3,785 full-regression tests (3,730 passed, 55 skipped); zero test failures/errors. The M7.4 module specifically returned 63 passed and 42 intentional skips in the generic interpreter, where graph-tool and SNAP task partitions are unavailable. The five-backend E.8.5/E.8.8 run `45395352748` separately passed all backend partitions, including graph-tool and isolated SNAP. The G9.42 detached report verifier, immutable evidence bundle publisher, catalog builder and independent catalog verifier all succeeded.

Report SHA-256: `d12a924d7da5c29334c1df8e40072671e5771bc733e9c3c65e1395311ff831db`. Content-addressed bundle SHA-256: `decb5aa79605dad7bab4067d6700e8490aa3193c91b069098f87aa8a216a6266`. Actions artifact: `14923188602`, archive digest `sha256:39a9be6f71e093d101c2eedc704a596ce816adb78d354c28ce8dac2dc0b5435d`.

G9.42 is now complete for this source snapshot. M7.4 is not complete: formal per-task/per-backend G1–G8 outcomes remain Insufficient evidence, the distinct E.8.5/E.8.8 artifacts still need their detached M7.4 G7 verifier pass, and representative task-domain workloads, G4/G6 closure and PATH/IMPACT boundaries remain. `production_approval=false` is unchanged.

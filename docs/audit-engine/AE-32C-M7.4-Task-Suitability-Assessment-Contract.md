# AE-32C M7.4 — Task-Specific Backend Suitability Assessment Contract

**Contract version:** `ae32c/m7-4-suitability-contract/v1`  
**Status:** Assessment contract defined; task-level suitability decisions not yet issued  
**Target branch:** `stage1/section-uuids` only  
**Baseline Stage1 source:** `47eb1ae6777e1d34c445af219c96840797739f23`  
**M7.2 campaign:** [run 44940960831](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44940960831)  
**M7.3 detached dossier verification:** [run 44945256220](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44945256220)  
**Authority:** `production_approval=false`; no global ranking, winner, automatic selector, scientific approval, graph mutation, or runtime promotion.

---

## 1. Purpose and decision question

M7.4 converts the accepted M7.1–M7.3 evidence into bounded, operation-specific suitability statements. It does not repeat the five-backend performance campaign and does not choose one library as the repository-wide default.

The decision question is:

> For one precisely identified audit-engine operation, under a declared graph shape, semantic contract, execution environment and operational policy, does a given computational backend have sufficient evidence to be considered suitable?

A backend may be suitable for one operation and unsuitable or unqualified for another. Multiple backends may be retained because they provide different computational representations and APIs.

The canonical `SemanticGraph` remains authoritative for semantic identity, directed typed edge occurrences, attributes, metadata, evidence and provenance. Backends remain replaceable computation projections under ADR-032.

## 2. Evidence baseline and limits

### 2.1 M7.2 evidence available

The accepted campaign used five deterministic workload families:

- `sparse_dependency`
- `hub_impact`
- `parallel_evidence`
- `disconnected_components`
- `dense_local_neighborhood`

Each backend report covered two seeds, five workloads, 15 measured repetitions and 5 warm-up calls per query. Across the five backends, the dossier records 3,750 timed observations and 1,250 warm-up observations. The five reports share graph fingerprints and corresponding query-result digests; preflight parity failures were zero and expected native query modes and adjacency telemetry were present.

These results support a bounded statement about the tested semantic-traversal primitive and generated graph shapes. They do not demonstrate that each higher-level audit operation has been exercised end-to-end through its public query/analyzer/service path.

### 2.2 M7.3 evidence available

M7.3 verified the detached artifacts for campaign run `44940960831`, attempt 1, source revision `1122916e8a56abec43cf3d42f8b2d252533e81c1`. The verifier checked artifact identity and expiry, report and log consistency, workload/seed coverage, graph and query-result digest parity, native-path evidence, sample arithmetic and environment strata.

M7.3 is an integrity and consistency dossier. It does not re-execute historical measurements, independently authenticate the physical runner, or turn artifact/report hashes into signed attestations.

### 2.3 Explicitly unavailable evidence

The current M7.2/M7.3 evidence does not qualify:

- sparse numerical linear algebra or finite-element solvers;
- centrality or other global graph algorithms;
- community detection;
- ontology reasoning or RDF/SPARQL workloads;
- complete repository evidence reconstruction;
- full audit-engine task latency;
- comparable process-level memory measurements;
- cross-backend performance rankings across the separate Azure/AWS runner environments.

No inference beyond these limits is permitted.

## 3. Audit-operation inventory

The Stage1 analysis engine currently registers four query/analyzer paths. M7.4 shall assess each as a distinct task; passing a shared traversal primitive is not sufficient to accept the complete operation.

| Task ID | Public query/analyzer path | Intended audit use | M7.4 starting evidence status |
|---|---|---|---|
| `T-STRUCTURAL` | `QueryType.STRUCTURAL` / `StructuralAnalyzer` | One-hop relationship-neighborhood inspection | Candidate; end-to-end backend-specific acceptance still required |
| `T-DEPENDENCY` | `QueryType.DEPENDENCY` / `DependencyAnalyzer` | Direct/transitive dependency context retrieval | Candidate; end-to-end backend-specific acceptance still required |
| `T-PATH` | `QueryType.PATH` / `PathAnalyzer` | Bounded path and associated evidence exploration | Candidate; domain-specific claim-to-evidence use must be verified separately |
| `T-IMPACT` | `QueryType.IMPACT` / `ImpactAnalyzer` | Multi-source change-impact candidate discovery | Insufficient evidence for complete operation; includes additional logic beyond the M7.2 traversal corpus |

### 3.1 Structural neighborhood

The analyzer performs a depth-one traversal with direction and relation filters. The suitability test must verify the public `GraphAnalysisEngine.execute` route, exact edge-occurrence/evidence output, direction semantics, self-loop handling and the configured backend's native adjacency telemetry.

### 3.2 Dependency context

The analyzer supports direction, relation filters and bounded depth/visited-node/step constraints. Its result is a structural observation, not a judgment that a dependency is valid, unsafe or prohibited. The assessment must test the analyzer and its public service route, not only the lower-level traversal method.

### 3.3 Path exploration

The analyzer finds a bounded path between a source and target and emits observations/evidence for the path steps. A generic graph path result must not be described as a validated claim-to-evidence reconstruction unless the relevant node/edge types, evidence identifiers, source locators and source-content follow-through are separately tested.

### 3.4 Change-impact candidates

The impact analyzer includes more than one traversal:
- multi-source impact analysis, with a maximum of 25 change sources;
- allocation of global visited-node and traversal-step budgets across sources;
- deterministic candidate merging and per-source attribution;
- ownership/evidence resolution;
- a separate bounded dependency-cycle scan (up to 2,000 cycle nodes and 50,000 scanned edges);
- incomplete/truncation and cycle-scan status reporting.

M7.2's common traversal queries do not by themselves qualify these additional behaviors. M7.4 must identify which of these sub-operations actually use the selected backend and which still operate over the canonical graph or separate indexes. Until this is tested, the complete impact operation is `insufficient evidence`, not accepted by extrapolation.

## 4. Per-backend implementation facts to carry into the assessment

These are implementation facts, not suitability verdicts.

| Backend | Implemented native query mechanism | Representation / operational qualification |
|---|---|---|
| NetworkX | Directed `MultiDiGraph`; local `succ`/`pred` adjacency; keyed parallel edge occurrences | Native graph retains edge attributes and multiedge identity. NetworkX has a distinct traversal path and must be tested through the same public analyzer/service routes as other backends. |
| SciPy | CSR outgoing rows and CSC incoming columns; exact semantic occurrences reconstructed through side channels | CSR stores connectivity and multiplicity; relation labels, attributes and provenance are retained in exact side channels. The sparse matrix alone is not the complete semantic representation. |
| python-igraph | Native incident edge IDs for incoming/outgoing queries | Edge identity and canonical occurrence mapping must remain one-to-one, including parallel edges and self-loops. |
| graph-tool | Native per-vertex `out_edges()` / `in_edges()` iterators and edge-index mapping | Property-map behavior and installed distribution/version are environment-specific and must be reported. |
| SNAP | TNEANet edge-ID queries through an isolated CPython 3.9 worker and versioned JSON-lines protocol | Requires Docker and a configured image; attributes are canonical-JSON encoded. Worker isolation, image identity, protocol bounds, failure handling and process lifecycle are part of suitability, not incidental setup details. |

### 4.1 SNAP-specific operational gap

The current Python worker adapter performs synchronous `stdout.readline()` calls in its request path without a per-request response deadline. Its close path has a bounded process wait, but that does not bound a stalled initialization, audit or adjacency request. The M7.3 campaign record also did not contain a concrete container image ID (`container_image_id=null`).

Therefore, SNAP cannot receive an unqualified operational suitability statement until a pinned image identity and bounded request/termination behavior are evidenced. This is a specific gap to assess and, if approved as a separate correction, remediate; it is not a claim that the observed campaign failed.

## 5. Suitability outcome vocabulary

Every task/backend pair must receive exactly one of these outcomes:

- **Suitable for this task:** all mandatory semantic, algorithmic, execution-path, environment and operational gates have direct evidence for the declared snapshot and workload envelope.
- **Conditionally suitable:** mandatory correctness gates pass, but one or more explicitly stated deployment, scale, environment or operational conditions restrict use.
- **Not suitable:** a mandatory task requirement is demonstrably unmet or the implementation cannot satisfy the operation's contract.
- **Insufficient evidence:** the relevant behavior has not been tested or the available evidence cannot support a bounded conclusion.

“Available”, “importable”, “adapter implemented”, or a capability flag is not a suitability outcome. A timing advantage is neither necessary nor sufficient for suitability.

## 6. Required record for every task/backend pair

Each suitability statement must contain:

1. **Task identity:** task ID, exact public query/analyzer/service entry point, intended audit purpose and caller(s).
2. **Input envelope:** node/edge counts, topology, degree distribution, direction, multiedge/self-loop frequency, relation vocabulary, attribute/metadata size and evidence density.
3. **Semantic obligations:** canonical identity preservation, edge-occurrence multiplicity, direction/filter behavior, deterministic ordering, provenance/evidence payloads, bounds, truncation and failure semantics.
4. **Native implementation:** exact library API used, source location, library/distribution version, and evidence that the API is called on the actual application execution path.
5. **Execution boundary:** whether the operation uses the backend for all sub-operations or mixes backend traversal with canonical-graph/index scans.
6. **Operational envelope:** Python/platform, dependency environment, worker/container identity, resource limits, startup/IPC costs, timeouts, cleanup and recovery behavior.
7. **Measured observations:** workload-specific raw samples and descriptive statistics where comparable; environment strata kept separate; no unsupported cross-environment ranking.
8. **Evidence references:** immutable source SHA, test/profile run IDs, campaign run/attempt, artifact IDs, report digests and limitations.
9. **Unsupported cases:** known exclusions, failure modes, fallback behavior and any conditions that invalidate the statement.
10. **Outcome and rationale:** one outcome from Section 5, with a short evidence-based explanation and explicit reassessment trigger.

## 7. Mandatory acceptance gates

A task/backend pair cannot be marked suitable unless all applicable gates pass:

- **G1 — Task definition:** exact operation, callers, inputs and output semantics are specified.
- **G2 — Semantic correctness:** independent expected-result fixtures cover the task's direction, relation filters, edge occurrences, self-loops, cycles, bounds and evidence/provenance obligations as applicable.
- **G3 — Public-path execution:** the actual analyzer and service route uses the declared backend; native API instrumentation proves the path. No silent Python fallback is allowed while the result reports a native backend.
- **G4 — Snapshot and mutation safety:** projection and query operations do not mutate the canonical graph or repository files; stale/corrupt projections fail closed.
- **G5 — Task workload:** the workload represents the named audit operation and its relevant graph characteristics. Generic traversal parity alone is not sufficient.
- **G6 — Environment and operations:** dependencies, native API versions, worker/container constraints, resource limits, timeout/cleanup/recovery behavior and known deployment restrictions are recorded.
- **G7 — Evidence integrity:** reports are bound to one exact source snapshot and test/campaign attempt; digests and provenance are independently checked within their stated limits.
- **G8 — Scope discipline:** no universal ranking, winner, global scalar score, automatic selection, scientific approval, graph mutation or production approval is inferred.

If a mandatory gate is untested, the result is `insufficient evidence`. A known unmet requirement is `not suitable`. Conditional suitability is allowed only when the remaining conditions are explicit, enforceable and do not weaken semantic correctness.

## 8. Selection and authority policy

M7.4 produces an evidence-backed suitability matrix and task-specific statements. It does not implement or activate runtime selection.

In particular:

- no backend is declared the universal default;
- no global score or cross-task ranking is produced;
- no automatic selector is authorized by benchmark data;
- no backend capability flag is treated as acceptance evidence;
- a requested backend must not silently fall back to another backend;
- the canonical `SemanticGraph` remains the authority;
- backend-specific projections may not create semantic identities or alter evidence;
- `production_approval=false` remains invariant.

Any future runtime selection policy requires a separate explicit architectural decision, with task requirements and failure behavior defined independently of M7 timing observations.

## 9. Initial assessment hypotheses — not decisions

The following are test priorities, not suitability conclusions:

- All five backends are candidates for the bounded traversal primitive exercised by M7.2.
- Structural neighborhood, dependency context and generic bounded path exploration are the first higher-level operations to test because they are directly composed from the shared traversal primitive.
- Change-impact analysis requires additional tests for multi-source allocation, candidate merging, ownership evidence and cycle scanning.
- SNAP requires image pinning and bounded worker request/termination behavior before operational suitability can be concluded.
- SciPy requires explicit tests proving that side-channel reconstruction preserves the semantic edge occurrence and payload contract; CSR/CSC connectivity alone is insufficient.
- RDFLib/OWL reasoning and numerical sparse solvers remain separate task families and are outside this M7.4 traversal suitability matrix unless separately scoped.

## 10. Exit criteria for M7.4

M7.4 is complete only when:

1. the task inventory is checked against the current public query/analyzer/service code;
2. each in-scope task has a declared workload envelope and independent expected-result fixtures;
3. every backend/task pair has a completed evidence record or an explicit `insufficient evidence` / `not suitable` outcome;
4. all claimed native paths are verified at the public operation boundary;
5. environment and worker limitations are disclosed without pooling incomparable timing samples;
6. the final matrix is reproducible from exact source/test/artifact references;
7. the roadmap and decision records state exactly which task-specific claims are supported and which remain open;
8. `production_approval=false` and all no-ranking/no-auto-selection constraints remain intact.

M7.4 does not require every backend to be suitable for every task. An honest `insufficient evidence` outcome is preferable to extrapolating from a benchmark that did not exercise the operation.

---

## 11. Code surfaces reviewed for this contract

- `audit_engine/semantic_audit/graph/analysis/engine.py` — registered public query/analyzer paths.
- `analysis/structural.py`, `analysis/dependency.py`, `analysis/path.py`, `analysis/impact.py` — task-level semantics and composition.
- `backend/adapter_interface.py` — typed native edge-occurrence adjacency contract.
- `backend/adapter_traversal.py` — non-NetworkX projection validation, native adjacency, canonical occurrence checks and reference parity.
- `backend/networkx_adapter.py`, `scipy_adapter.py`, `igraph_adapter.py`, `graph_tool_adapter.py`, `snap_worker_adapter.py` — concrete native APIs and operational boundaries.
- `backend/capability_registry.py`, `backend/backend_selector.py`, `backend/backend_factory.py`, `backend/backend_pipeline.py` — capability declaration and construction/selection boundary.
- `tools/gb06_task_suitability_campaign.py`, `tools/gb07_campaign_dossier.py` and their tests — campaign and detached-dossier evidence.

**Contract conclusion:** M7.4's scope is sufficiently defined to begin task-level assessment design. No task/backend suitability verdict is issued by this contract alone.

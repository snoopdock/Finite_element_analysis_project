# AE-32C M7.4 — Task-Specific Backend Suitability Assessment Contract

**Contract version:** `ae32c/m7-4-suitability-contract/v1`  
**Status:** Expanded M7.4 task acceptance passed across all five backends; exact-source G9.42 passed at Stage1 SHA `d66f10b5c8af74b33a661c2453da3aca9982d565` in run `45400741779`; the E.8.5/E.8.8 artifact-integrity gate G7 is closed; all 20 formal task/backend outcomes remain Insufficient evidence pending remaining semantic, mutation-safety, workload, operational and task-domain gates  
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
| `T-STRUCTURAL` | `QueryType.STRUCTURAL` / `StructuralAnalyzer` | One-hop relationship-neighborhood inspection | Initial synthetic public-service acceptance passed across five backends; formal verdict pending |
| `T-DEPENDENCY` | `QueryType.DEPENDENCY` / `DependencyAnalyzer` | Direct/transitive dependency context retrieval | Initial synthetic public-service acceptance passed across five backends; formal verdict pending |
| `T-PATH` | `QueryType.PATH` / `PathAnalyzer` | Bounded path and associated evidence exploration | Initial synthetic public-service acceptance passed across five backends; domain-specific claim-to-evidence and formal verdict remain pending |
| `T-IMPACT` | `QueryType.IMPACT` / `ImpactAnalyzer` | Multi-source change-impact candidate discovery | Initial multi-source public-service acceptance passed across five backends; canonical cycle scan and formal verdict remain pending |

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

M7.2's common traversal queries do not by themselves qualify these additional behaviors. The first M7.4 IMPACT test tranche now exercises multi-source merging, source attribution, per-source paths, ownership evidence, cycle evidence and budget/status behavior through the public service across all five backends. Source inspection confirms a hybrid execution boundary: ownership resolution and reverse-dependency walks use the selected traversal engine, while `_dependency_cycles` sorts and scans the canonical `SemanticGraph.edges` collection (subject to the 50,000-edge guard), then filters the induced impacted-node subgraph before its iterative SCC analysis. The cycle scan is therefore not a native backend operation. The new tests establish initial synthetic behavior, but they do not complete the representative workload, operational and G1–G8 evidence required for an IMPACT suitability verdict.

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

The M7.3 campaign record did not contain a concrete container image ID (`container_image_id=null`); the M7.4 follow-up runs record run-specific Docker image identities. The unbounded request wait has now been corrected in Stage1 source `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86`: `_request` bounds both pipe write/flush and response read, with a configurable 120-second default and 600-second maximum; graceful close is capped at five seconds. Timeout cleanup uses the Docker container ID captured by `--cidfile`, attempts `docker rm --force` with a two-second subprocess timeout, and then bounds host-client termination/kill. The adapter enters a terminal state after timeout; automatic worker restart is not implemented. The SNAP adapter test step passed in exact-source run `45385374806`, but the forced-removal path is tested with simulated process/Docker calls rather than a live deliberately stalled container. The SNAP repository-backed E.8.8 stage in that run remains in progress at the last inspection, so live repository conformance must not be marked accepted from this run.

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

### 8.1 Existing selector behavior is not an approval mechanism

The Stage1 code currently has a policy/implementation distinction that must remain visible during M7.4:

- `BackendCapabilityRegistry` marks `semantic_traversal=True` for the five registered options while each `acceptance_state` still reports API compatibility and conformance as `not_checked` / `not_run`.
- `BackendSelectionPolicy.find_backends()` filters on availability and requested capability values; it does not require the corresponding acceptance-state gates to have passed.
- `BackendSelectionPolicy.select()` returns the first matching candidate when `preferred_backend` is omitted. That is an implicit first-match selection behavior in the current implementation.

This contract does **not** treat that behavior as authorized automatic selection or as evidence that the first candidate is suitable. The native traversal engine currently supplies an explicit preferred backend for its backend-specific execution path, but the generic selector API remains capable of implicit selection. Before any runtime selector is relied upon, a separate correction/ADR must define task-to-capability requirements, require task-specific acceptance evidence, define deterministic failure behavior, and remove or explicitly govern implicit first-match selection. M7.4 itself will not silently change this runtime behavior; it will record the mismatch and keep the authority boundary explicit.

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
- `tests/semantic_graph/test_m74_task_suitability_acceptance.py` — initial public-service STRUCTURAL, DEPENDENCY and PATH task acceptance tests.
- `validation/profiles/G9.42.yaml` — deterministic profile inclusion for M7.4; exact-source dispatch passed at Stage1 SHA `d66f10b5c8af74b33a661c2453da3aca9982d565` in run `45400741779`.
- `.github/workflows/e85-native-graph-backend-conformance.yml` — backend-isolated M7.4 test execution across NetworkX, SciPy, igraph, graph-tool and SNAP worker environments.

## 12. Initial task-level executable evidence — 2026-11-24

The first implementation tranche is committed at Stage1 source SHA `942b54f8948286b4727ca208fdfa553e019437b9`. It adds `tests/semantic_graph/test_m74_task_suitability_acceptance.py`, includes the module in `validation/profiles/G9.42.yaml`, and inserts a backend-scoped test step into each of the five existing E.8.5/E.8.8 native-backend workflow environments.

The push-triggered [workflow run 45381213888](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45381213888) checked out the exact source commit above in all five backend jobs. Each selected-backend test invocation reported 7 passed and 28 skipped. The skips are deliberate: each job sets `AE32C_M74_BACKEND` to one backend and skips the four other backend partitions. Across the five environments this produced 35 passing backend-specific task test executions, not 35 distinct test definitions. All five E.8.5/E.8.8 native conformance jobs and the aggregate summary also succeeded.

### 12.1 Tested operation behavior

- **STRUCTURAL:** one-hop public-service analysis, direction and relation filtering, exact duplicate-endpoint/duplicate-relation edge-occurrence evidence, incoming and bidirectional direction, and one-count self-loop behavior.
- **DEPENDENCY:** bounded transitive traversal across `IMPORTS` and `DEPENDS_ON`, exclusion of the decoy `USES` relation, exact observation/evidence output, and explicit incomplete status under a traversal-step limit.
- **PATH:** bounded source-to-target path output with path-step evidence, exclusion of a filtered direct edge, and incomplete/no-false-path behavior when the step budget stops traversal.

Each backend run compares task results against the reference service, asserts the declared native query mode and nonzero native adjacency lookup/edge-occurrence telemetry, requires per-query reference parity and zero query failures, and checks that the canonical `SemanticGraph` is unchanged. The fixture is deliberately diagnostic rather than representative: five nodes and seven edge occurrences, including two parallel same-label edge occurrences, one relation-filter decoy, a transitive chain, an incoming edge and a self-loop.

### 12.2 Backend execution record

| Backend | Workflow job | M7.4 test result |
|---|---:|---:|
| NetworkX | `138400416078` | 7 passed; 28 other-backend cases skipped |
| SciPy | `138400415869` | 7 passed; 28 other-backend cases skipped |
| python-igraph | `138400415873` | 7 passed; 28 other-backend cases skipped |
| graph-tool | `138400416016` | 7 passed; 28 other-backend cases skipped |
| SNAP isolated worker | `138400415896` | 7 passed; 28 other-backend cases skipped |

The aggregate E.8.5/E.8.8 summary job `138400786827` succeeded. The SNAP worker image was built and its run-time image ID was recorded as `sha256:f94d166165f7676f031bb476a79b0c7e112ef65f0f9c4ef5027844891f1eb4b3`. This is the Docker image content ID for that run; it is not a guarantee that future builds from mutable upstream inputs will reproduce the same image.

### 12.3 Scope and evidence limitations

This tranche provides initial semantic and native-path evidence for these three public service tasks. It does **not** issue a formal suitable/conditionally suitable/not suitable verdict for any task/backend pair. In particular:

- the fixture is small and synthetic; it does not establish behavior across the complete M7.2 workload envelope, production-sized graphs, resource pressure or realistic audit datasets;
- PATH is generic graph path/evidence traversal; claim-to-evidence reconstruction and hash-verified source-content follow-through remain separate obligations;
- IMPACT is not covered and remains `insufficient evidence` pending direct tests of multi-source budgeting, candidate merging, ownership/evidence resolution, cycle scanning and truncation reporting;
- the SNAP image identity is now recorded for this run, but synchronous worker `stdout.readline()` still has no per-request response deadline; timeout, termination and recovery behavior remain open;
- the generic backend selector's implicit first-match behavior and acceptance-state enforcement are not changed by this tranche;
- G9.42 now includes the test module, but **G9.42 was not run** against this commit. The evidence cited here is the E.8.5/E.8.8 push workflow and its M7.4 test-step logs.

The next assessment work must expand operation-specific workloads and records, complete the IMPACT route separately, and close SNAP worker deadline/cleanup evidence before any stronger operational claim. No global ranking or automatic backend selection is introduced. `production_approval=false` remains invariant.

## 13. IMPACT task-level executable evidence — 2026-11-24

The follow-up implementation extends `tests/semantic_graph/test_m74_task_suitability_acceptance.py` with four IMPACT test cases for each backend. The tests execute through `SemanticGraphAnalysisService` and the registered `ImpactAnalyzer`, with reference parity enabled.

The corrected test commit is `ff6fe8226d6417b0832a17b8bed397217f72a303`. Exact-source [workflow run 45382782600](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45382782600) completed successfully. Each backend environment reported 11 passed and 44 intentionally skipped (the four non-selected backend partitions). This is 55 passing test executions across the five jobs for the complete M7.4 module, including the STRUCTURAL / DEPENDENCY / PATH cases already introduced in the first tranche. The five native E.8.5/E.8.8 backend jobs and aggregate summary all succeeded.

The IMPACT assertions cover:
- multi-source change-set attribution and deterministic output under source-order permutation;
- merging a shared candidate and retaining a separate path and source attribution for each changed source;
- depth-one file ownership evidence and classification of affected test, workflow and symbol candidates;
- dependency-cycle SCC output with exact cycle-edge evidence and the expected `IMPORTS` / `DEPENDS_ON` relations;
- allocation and enforcement of a global visited-node / traversal-step budget, with explicit `INCOMPLETE` results;
- an exceeded cycle-scan edge limit producing `incomplete_edge_limit` rather than a complete cycle result;
- rejection of duplicate change sources and change sets larger than 25 sources.

The initial run at commit `b6b81b60753cf36334281f19c3ff64aea5abe7b9` failed because the test expected `MEMBER_OF` in the evidence produced by a file-source ownership resolution. That relation is a second-hop edge from the symbol found by the one-hop file ownership walk; the expectation exceeded the implementation's declared depth-one ownership behavior. The correction in `ff6fe8226d6417b0832a17b8bed397217f72a303` narrowed the asserted evidence set to the direct ownership occurrences. No analyzer/runtime implementation was changed in response to that failure. The corrected test suite then passed in all five environments.

The backend is involved in the ownership and reverse-dependency traversal queries. The subsequent dependency-cycle scan is a separate canonical-graph operation, not a selected-backend SCC API. The small fixture and monkeypatched edge-limit test establish deterministic bounded behavior, not performance or suitability of a native SCC implementation. The same graph-size/workload limitations stated in Section 12 continue to apply.

The SNAP run recorded Docker image ID `sha256:8aa923b1de4d7b2ca7301cb27556178e35e8c54cff433f0c5d653320637f089e`. Per-request response deadlines, timeout propagation, termination and recovery are still not demonstrated. G9.42 includes the M7.4 test file but was not dispatched against this source commit. IMPACT therefore has initial synthetic acceptance evidence, not a final task/backend suitability verdict.

**Contract conclusion:** M7.4 now has initial executable STRUCTURAL / DEPENDENCY / PATH / IMPACT task-acceptance evidence across all five backends. The evidence is bounded to synthetic fixtures and the tested run environments; the IMPACT cycle scan is a canonical-graph sub-operation rather than a native backend operation. Formal task/backend suitability verdicts remain pending. G9.42 and the outstanding workload, selector and SNAP operational gates are not closed by these test runs.


## 14. SNAP timeout implementation and current live-run boundary — 2026-11-24

The worker request-deadline implementation and follow-up corrections are committed at:

- `2755043ba5f985225c8794c93d72b76567ff8b83` — bounded request/close RPC;
- `fe6b5474be56f769309f66a4e56f82a44c1890bf` — Docker container ID capture and forced-removal path;
- `f03d2768b3863f74719079e7cde458b02f2b87b4` — timeout test setup correction;
- `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86` — constructor initialization-order correction.

The current adapter enforces `AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS` (default 120 seconds; maximum 600 seconds) across both request pipe write/flush and response read. Graceful close uses a five-second cap. The adapter captures the Docker container ID with `--cidfile`; on a timeout it attempts `docker rm --force` against that exact ID, then terminates/kills the Docker client with bounded waits, closes streams and removes its temporary directory. It does not automatically restart a worker.

The SNAP adapter protocol test step passed at exact-source run `45385374806`, as did the SNAP M7.4 task test and synthetic E.8.5 conformance steps. The four non-SNAP backend jobs passed. The repository-backed SNAP E.8.8 step was still in progress after approximately 35 minutes at the last inspection, with no final result or SNAP evidence artifact available. Consequently, the current revision has positive adapter unit-test evidence but no current-run repository-backed SNAP acceptance result.

The timeout and container-removal unit tests use simulated process/Docker behavior. They do not prove that a real Docker daemon removes a deliberately stalled container. A Docker-backed lifecycle test and exact-revision G9.42 are still outstanding. No final task/backend suitability verdict is issued by this follow-up.

## 15. Live SNAP timeout cleanup and E.8.8 boundary — 2026-11-24

**Exact source:** `7a77b52c316c60ffb8f433af2bbd1b742f389972`  
**Workflow:** [run 45391619634](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45391619634)

The workflow now executes `tests/semantic_graph/test_snap_worker_docker_lifecycle.py` against a real Docker daemon. The live Docker lifecycle test `tests/semantic_graph/test_snap_worker_docker_lifecycle.py` passed. It built a disposable worker container that deliberately did not respond, observed the adapter request deadline, verified `docker rm --force` used the exact container ID captured by `--cidfile`, and confirmed that `docker inspect` could no longer find the container. This is direct live Docker evidence on the tested GitHub-hosted runner, not merely a mocked process test.

In exact-source workflow run `45391619634` at `7a77b52c316c60ffb8f433af2bbd1b742f389972`, the SNAP adapter protocol/restriction tests, live Docker timeout cleanup test, M7.4 task suite and synthetic E.8.5 all succeeded. NetworkX, SciPy, python-igraph and graph-tool jobs also succeeded. At the last inspection, SNAP repository-backed E.8.8 remained `in_progress` after approximately 12 minutes; no final SNAP repository report or artifact was available. Do not count the matrix as complete.

The E.8.8 command is configured with a 30-second worker RPC timeout and a 12-minute step timeout. Its continuing `in_progress` status at the last inspection is unresolved; no SNAP E.8.8 report or artifact was available. Do not infer acceptance from the earlier E.8.5 pass.

The G9.42 profile now includes `tests/semantic_graph/test_snap_worker_adapter.py`, `tests/semantic_graph/test_snap_worker_docker_lifecycle.py`, and `tests/semantic_graph/test_m74_task_suitability_acceptance.py`. Exact-source G9.42 has not been dispatched. The default-branch manual dispatcher is `workflow_dispatch` only, and the available GitHub connection does not expose a workflow-dispatch action.

The formal G1–G8 task/backend evidence records and suitability verdicts remain pending. Keep `production_approval=false`.


## 16. Expanded M7.4 seeded task workloads and completed E.8.5/E.8.8 matrix — 2026-11-24

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

### 16.1 Completed SNAP repository conformance and resource lifecycle

The preceding exact-source run `45391619634` had produced a semantically complete E.8.8 JSON report but the command did not exit; the step timed out after 12 minutes because the runner did not explicitly close the `RepositoryEvidenceTools` backend adapter. The correction adds `RepositoryEvidenceTools.close()` and wraps the E.8.8 runner in `try/finally`. Phase logs now record repository indexing, query completion, source-hash follow-through, context traversal, resource closure and report completion. In the successful run, the logs explicitly reached `backend_resources_closed` before report output.

The SNAP E.8.8 report completed with `status: passed` and source SHA `51d025fd328b00a59988a05fe72d9092262434f5`. It records 43 attempted/successful backend queries, 43 reference-parity verifications, zero query failures and zero parity failures; 45 native adjacency lookups and 86 native edge occurrences read. The repository fixture is complete: 26 nodes, 41 edge occurrences, 9 indexed files, graph fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`, and source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. The runner followed graph-surfaced paths to two source reads (`main.py` and `tests/checks.py`) and verified both SHA-256 values.

The per-operation context telemetry is also complete: trace context 7/7 parity-verified adjacency queries; workflow context 16/16; nested workflow context 16/16. The SNAP worker was CPython 3.9.25 / SNAP 6.0.0, image ID `sha256:a3ab78cf8512048adfc3570bff591772c1542dfb09226363142c6779934f59a5`, with the declared isolated container restrictions. E.8.8 used a 30-second worker request deadline.

SNAP's test job also passed the adapter protocol/restriction tests, live Docker timeout/cleanup test, repository backend resource-teardown contract test, and synthetic E.8.5. The SNAP artifact is ID `14920592009`, archive digest `sha256:e5ff53b2ee4d86c7534d080bf96558618445a8d7d4281e6f854a3c0bd45eac30`. All five backend jobs and the aggregate summary concluded `success`.

### 16.2 Test-oracle correction in the expanded tranche

The first expanded run at `f31c29b518411f09142b967b3120e9f666179679` correctly exposed that the new fixture passed `max_depth=6` to IMPACT, while `ImpactAnalyzer` enforces a maximum depth of 5. The ten seeded cases failed in each tested backend at that shared analyzer input guard; the failure occurred before a backend parity comparison. The test was corrected to `max_depth=5` at `51d025fd328b00a59988a05fe72d9092262434f5`. The corrected matrix passed all five backends. No analyzer/runtime algorithm was changed for this test-oracle correction.

### 16.3 Limits of this evidence

The expanded workloads are medium-sized seeded semantic fixtures with disjoint replicated subgraphs; they are not production graph captures, latency measurements, memory profiles or a representative audit corpus. PATH remains generic graph path/evidence exploration, not complete domain-specific claim-to-evidence reconstruction. IMPACT cycle detection remains a canonical-graph SCC operation rather than a native backend SCC query. Formal G1–G8 per-task/per-backend records and verdicts remain pending. At the time this section was prepared, exact-source G9.42 was still pending; it was subsequently passed on Stage1 SHA `d66f10b5c8af74b33a661c2453da3aca9982d565` in run `45400741779` (Section 18). Retain `production_approval=false`.


## 17. Preliminary 20-pair evidence ledger

The current evidence is consolidated in [AE-32C M7.4 Preliminary Task/Backend Evidence Matrix](AE-32C-M7.4-Preliminary-Task-Backend-Evidence-Matrix.md). It enumerates all four public tasks against all five computation options, records the bounded positive test/native-path evidence, and assesses each G1–G8 gate. At the time the preliminary ledger was first recorded, detached G7 verification was outstanding. It was subsequently completed for the five-backend E.8.5/E.8.8 artifact set (Section 19). All 20 preliminary outcomes remain Insufficient evidence because semantic boundary coverage, representative audit workloads, mutation-safety and operational envelopes, and PATH/IMPACT task-domain qualifications remain incomplete. The ledger is not a suitability approval and does not promote a backend.

## 19. M7.4 G7 detached evidence verification — 2026-11-24

The five backend E.8.5/E.8.8 evidence artifacts from [run 45395352748](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45395352748) were downloaded by exact Actions artifact ID and independently checked against the GitHub Actions archive metadata. The detached verifier is committed as `tools/gb08_m74_native_conformance_dossier.py`, with adversarial unit tests at `tests/semantic_graph/test_m74_detached_native_conformance_dossier.py`.

All five artifact sizes and SHA-256 digests matched; each ZIP contained exactly its expected E.8.5 and E.8.8 JSON reports. Source SHA/run/attempt, backend/library/native-mode identity, parity/telemetry, semantic case sets, projection round-trip, repository graph fingerprint/manifest, two source-read hashes, side-effect declarations and SNAP worker restrictions were verified. Each backend reported 14/14 E.8.5 and 43/43 E.8.8 parity-verified queries with zero failures. All 11 verifier unit tests passed.

Manifest SHA-256 `ff13bff4d7b2f57e425e2566b90797cbd22016ec048926e9ea590f67e79444d3`; verified dossier SHA-256 `43137fb5a2ad24bb3afbd522b2b6445959501560abc001845b6051141710437a`. Full interpretation and reproduction steps are in [the detached dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier.md).

**G7 conclusion:** Pass for the exact artifact set from run 45395352748. This is detached byte/digest and report-consistency verification, not historical workflow re-execution or physical-runner attestation. G2/G4/G5/G6 and task-domain qualification remain open. All 20 task/backend outcomes remain Insufficient evidence and `production_approval=false`.

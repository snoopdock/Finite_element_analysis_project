# AE-32C M0 — Architecture Baseline and Traceability Close-out

**Status:** M0 closed as a source-to-test traceability baseline; implementation/conformance gaps remain explicitly assigned to M1–M3  
**Target branch:** `stage1/section-uuids` only  
**Pinned Stage1 snapshot:** `1ed0471832b660e8c29a946e4655e1ed981106bf` — E.8.8.2  
**Validation evidence:** Manual Validation Dispatcher run `44885166907`, profile `G9.42`, regression mode `profile`  
**Scope:** AE-32C graph backend architecture, adapters, query execution, evidence tools, tests, workflows, dependency environments and decision-record traceability

---

## 1. Executive result

M0 is closed as an inventory and traceability milestone. The current Stage1 source snapshot is pinned, the adapter path is mapped from registry/factory through traversal and evidence tools, existing tests are classified by the claims they support, workflow execution and artifact boundaries are recorded, backend environment assumptions are identified, and decision-record numbering anomalies are catalogued.

**M0 closure is not backend acceptance.** It does not certify SciPy, igraph, graph-tool or SNAP for native query execution. It does not complete the M1 adapter protocol, establish all independent behavioral or fault-injection tests, or constitute an E.8.5/E.8.8 multi-backend workflow run.

The E.8.8.2 implementation has passed the requested G9.42 manual validation on the exact Stage1 commit. The workflow log checked out `stage1/section-uuids` at `1ed0471832b660e8c29a946e4655e1ed981106bf`, selected `G9.42` with `profile` regression mode, reported targeted and regression execution as passed, and verified the evidence integrity/outcomes. The dispatcher itself ran from `main`; that is the validation engine location, not the branch under test. No Stage1-to-main merge or main-branch modification is implied.

## 2. Pinned execution and validation evidence

| Item | Evidence |
|---|---|
| Target branch | `stage1/section-uuids` |
| Tested source SHA | `1ed0471832b660e8c29a946e4655e1ed981106bf` |
| Validation workflow | `.github/workflows/00_manual_validation_dispatcher.yml` on `main` |
| Run | [44885166907](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44885166907) |
| Inputs | branch `stage1/section-uuids`; profile `G9.42`; regression mode `profile` |
| Targeted tests | Passed; exit code 0 |
| Regression tests | Passed; exit code 0 |
| Evidence integrity/outcome verification | Passed |
| Provenance catalog | Built and independently verified |
| Artifact | `manual-validation-evidence-44885166907-1` (170,043 bytes) |

The inspected logs establish these facts. They do not expose a test-count summary in the relevant lines inspected; this report therefore does not invent a count. This run is G9.42 evidence for the E.8.8.2 commit. It is not a run of the separate E.8.5/E.8.8 native-backend conformance workflow.

## 3. Runtime architecture trace

The implementation path is:

```text
RepositoryEvidenceTools
  -> SemanticGraphAnalysisService
  -> configured backend selection
  -> BackendSelectionPolicy / BackendFactory / BackendPipeline
  -> backend traversal engine
  -> canonical GraphQuery / TraversalResult semantics
  -> evidence/provenance construction
  -> bounded source-read tool
```

Confirmed routing at the pinned snapshot:

| Tool or layer | Current route | M0 classification |
|---|---|---|
| `graph_neighbors` and dependency/impact variants | `GraphQuery` -> `SemanticGraphAnalysisService` -> configured traversal engine | Backend-routed; query behavior and evidence covered by service/tool tests |
| `graph_path` | `GraphQuery` -> configured traversal engine | Backend-routed |
| Graph-backed portion of `find_related_tests` | Graph query through configured traversal engine; lexical/source-reference scan is a separate evidence source | Hybrid route; report graph and lexical evidence separately |
| `trace_execution_context` | E.8.8.2 now requests local adjacency through the selected NetworkX engine; preserves import filtering and context-specific BFS/provenance | NetworkX context route covered by repository conformance |
| `find_workflow_context` | E.8.8.2 now requests local adjacency through the selected NetworkX engine; preserves workflow relations and bounded path search | NetworkX context route covered by repository conformance |
| Non-NetworkX context tools | The generic native traversal engine does not yet expose the E.8.8.2 `context_edges` operation; fallback is recorded as a backend bypass | Not accepted as native context routing |
| Runtime report | NetworkX reports cached projection information and query telemetry; generic non-NetworkX reporting still performs full native node/edge reads | Observability gap assigned to M1/M3–M6 |

The canonical `SemanticGraph` remains the semantic authority. The backend is a computational projection. Deterministic ordering, bounds, evidence interpretation and reference comparison remain in AE-32.

## 4. Existing tests mapped to the conformance claims

This is a source-level mapping of assertions and test scopes, not a claim that every optional native environment ran in the G9.42 job.

| Test module / runner | Existing evidence | What it does not establish |
|---|---|---|
| `tests/semantic_graph/test_e82_networkx_traversal_backend.py` | Directed `MultiDiGraph`; parallel edge preservation; canonical graph unchanged by projection; direction/depth/relation-filter combinations; reference parity; stale-graph and dangling-edge rejection; service metadata | Independent expected self-loop occurrence count; exhaustive native API interaction; defensive-copy guarantees for direct adapter use |
| `tests/semantic_graph/test_e88_networkx_repository_backend.py` | Forbids full NetworkX edge enumeration during query; checks native adjacency counters; repository graph-to-source hash follow-through; snapshot and side-effect assertions; after E.8.8.2, requires native context/workflow adjacency telemetry and zero context bypasses | Equivalent native-adjacency proof for other libraries |
| `tests/semantic_graph/test_e85_native_backend_conformance.py` and `tools/gb03_native_backend_conformance.py` | Five-node/eight-occurrence adversarial graph; three parallel occurrences; self-loop, cycle, isolated node, Unicode and nested payloads; seven query scenarios repeated twice; 14 reference parity checks when the real library is installed | Independent expected traversal outputs for every scenario; local native adjacency interaction proof; lifecycle/fault-injection matrix |
| `tests/semantic_graph/test_e83_multi_backend_traversal.py` | Fake-module/API contract tests, selection and error paths, side-channel corruption checks, optional real-library checks | Fake modules are not native conformance; availability/capability assertions do not establish acceptance |
| `tests/semantic_audit/test_ae32b_backend_runtime.py` | Trusted backend configuration, NetworkX/SciPy query counters, explicit reference mode, no LLM backend selection, fail-closed unsupported selection | Which concrete native data-structure methods were called or whether full-graph enumeration occurred |
| `tests/semantic_audit/test_ae32b_evidence_tools.py` | Tool catalog, graph observations, source provenance, bounded reads, import/workflow context semantics, truncation, deterministic snapshots and side-effect boundaries | Before E.8.8.2, context semantics did not prove backend routing; current NetworkX routing is separately asserted in E.8.8 tests |
| `tests/semantic_audit/test_ae32b_impact_dependency_tools.py` | Direct/transitive dependencies, reverse impact candidates, related tests and stable tool registration | Native interaction beyond the selected query engine |
| `tests/semantic_audit/test_ae32c_patch2_graph_workflow_fidelity.py` | Workflow command parsing, dynamic/non-root working-directory exclusions, source-root/module resolution, type-checking import classification, related-test matching and budget/truncation semantics | Native backend adjacency interaction |
| `tools/gb04_repository_backend_conformance.py` | Repository evidence-index completeness; graph-neighbor/path/related-test queries; source hash follow-through; context tool execution telemetry; no code execution/provider/network/source-write side effects | Multi-backend context conformance is not yet implemented. The current report's context `backend_execution` label is hard-coded to the NetworkX mode and must become backend-derived before it can serve as a general multi-backend report |

### 4.1 Semantic gap that must remain visible

The current Python reference traversal's `BOTH` expansion collects incoming and outgoing candidates separately. A self-loop can therefore be observed twice in the reference steps/examined-edge count, even though evidence may be deduplicated. The M1 specification recommends that a `BOTH` query return each edge occurrence once. This is a proposed normative correction, not yet implemented or validated. Independent expected-result tests must be added before changing the reference and native implementations together.

### 4.2 Scope of the G9.42 pass

G9.42 proves that the declared profile and regression targets passed for the pinned E.8.8.2 source commit. It does not replace the dedicated E.8.5/E.8.8 native workflow, nor does it prove that optional backend packages were provisioned and exercised in their dedicated environments.

## 5. Native adapter and API inventory

| Backend | Projection and current query behavior | Environment/API boundary | Status at pinned snapshot |
|---|---|---|---|
| NetworkX | Directed `MultiDiGraph`; keyed `succ`/`pred` adjacency; occurrence identity stored on native edges; E.8.8.2 routes both context tools through this engine | Python 3.11; `networkx>=3.2,<4.0` | Strongest integration; G9.42 passed for E.8.8.2; dedicated E.8.5/E.8.8 workflow still not evidenced here |
| SciPy | CSR connectivity plus canonical occurrence/relation/metadata side channels; adapter `neighbors()` reads one CSR row but returns distinct neighbors; generic traversal still validates/materializes full native node/edge collections | Python 3.11; `scipy>=1.11,<2.0` | Projection/query adapter exists; native exact edge-occurrence adjacency not implemented |
| python-igraph | Directed `igraph.Graph`; edge attributes include semantic occurrence; current readback iterates `graph.es` | Optional `igraph>=0.11,<2.0`; installed explicitly in the E.8.5 workflow | Native projection exists; per-vertex incident edge-ID query interface not implemented |
| graph-tool | Directed `graph_tool.Graph`; vertex/edge property maps; current readback iterates all vertices/edges; object properties are in-memory only | Separate Conda environment: Python 3.11, `graph-tool-base=3.9` | Native projection exists; local incident-edge query interface not implemented |
| SNAP | TNEANet; nested attributes/metadata canonical-JSON encoded; current readback iterates all nodes/edges | Isolated `snap-stanford==6.0.0` CPython 3.9.19 probe; main project requires Python >=3.11 | Compatibility probe only; not an accepted main-runtime adapter; worker protocol and repository parity absent |
| RDFLib | RDF interchange/SPARQL subsystem, separate from the five-backend traversal matrix | `rdflib>=7.0,<8.0` | Out of scope for this backend acceptance matrix |

### 5.1 Contract and capability gap

At the pinned snapshot, `SemanticGraphAdapter` formally declares only `export()`, `capabilities()`, `identity_mapping()` and `loss_report()`. Traversal additionally assumes `iter_native_nodes()` and `iter_native_edges()`, which are supplied by concrete classes/mixins rather than the abstract interface. No backend-neutral typed per-node edge-occurrence operation is part of the interface.

The generic `NativeAdapterMixin.neighbors()` scans its saved Python projection and returns distinct outgoing neighbor IDs. It does not constitute native edge-occurrence adjacency. The generic `NativeAdapterGraphTraversalEngine` builds Python outgoing/incoming dictionaries from full native node/edge readback; `walk()` and `runtime_report()` can repeat this full enumeration. Its runtime counters do not fully represent every full read performed by reporting.

The capability registry marks `semantic_traversal=True` based on registration and availability, not the full conformance ladder. These flags must not be interpreted as production acceptance.

## 6. Workflow, test invocation and artifact traceability

### 6.1 Dedicated native workflow

`.github/workflows/e85-native-graph-backend-conformance.yml` is `workflow_dispatch` only. It defines:

- Python 3.11 pip matrix for NetworkX, SciPy and igraph;
- a separate Python 3.11 Conda job for graph-tool;
- a separate CPython 3.9.19 SNAP 6.0.0 compatibility probe;
- synthetic runner `tools/gb03_native_backend_conformance.py`;
- repository runner `tools/gb04_repository_backend_conformance.py`;
- JSON report artifact upload with `if: always()`, 30-day retention;
- a summary job that fails if the pip matrix, graph-tool job or SNAP compatibility probe fails.

The SNAP job explicitly labels its result as a Python 3.9 worker candidate, not adapter acceptance. That distinction is correct.

**Important integration mismatch:** the workflow invokes the repository runner for SciPy, igraph and graph-tool as well as NetworkX. At this snapshot, the runner requires native context-tool routing and zero context bypasses, while only the NetworkX engine implements the E.8.8.2 context adjacency API. The generic non-NetworkX engine therefore cannot satisfy that gate. The runner also emits a literal NetworkX execution label for context operations. This is not a valid general multi-backend acceptance report. Before the workflow is used as a matrix acceptance gate, make the scope backend-aware: either mark context routing as an explicit not-yet-in-scope gate for those backends, or implement the corresponding backend-neutral protocol and native operations. Do not weaken the NetworkX assertions.

### 6.2 G9.42 dispatcher

The successful run used the dispatcher on `main`, which checked out the requested Stage1 branch at the exact pinned SHA. Its job ran the central validation engine's independent tests, the selected G9.42 targets and profile regression, verified evidence digests/checksums, published the evidence bundle, and independently verified the provenance catalog. This is the validation evidence for E.8.8.2, not evidence that the E.8.5/E.8.8 workflow matrix has run.

### 6.3 Workflow limitations

The Stage1 branch's own `e85-native-graph-backend-conformance.yml` remains manual. The GitHub integration used for this audit can inspect runs and logs but cannot dispatch this workflow. No claim is made that it has been run on the pinned SHA.

## 7. Decision-record inventory and reconciliation

The `docs/decisions/` directory contains distinct documents reusing ten ADR identifiers. The pairs have different titles and decision scopes; they are not safely treated as duplicate copies or automatic supersession pairs.

| Reused ID | Distinct records and scope |
|---|---|
| ADR-035 | Graph visualization boundary / verification boundary |
| ADR-036 | Evidence state machine / semantic verification boundary |
| ADR-037 | Candidate-knowledge isolation / separation of evidence state from verification decision |
| ADR-038 | Candidate-knowledge isolation / immutable verification receipts |
| ADR-039 | Semantic-context versioning / immutable verification receipts |
| ADR-044 | Impact-aware invalidation and recheck semantics / NetworkX query runtime integration |
| ADR-045 | Append-only audit-memory ledger / unified native graph-adapter traversal |
| ADR-046 | Evidence-bound graph impact analysis / incremental impact propagation |
| ADR-047 | SciPy side-channel parity / incremental re-verification planning boundary |
| ADR-048 | Audit-memory query model / native graph-backend conformance and acceptance states |

**Reconciliation decision:** do not rename or renumber these records in M0. The current source shows distinct subjects, and a safe canonicalization requires a repository-wide inbound/outbound cross-reference migration with historical provenance. Until that is separately approved, cite the full filename/title, not the numeric ADR identifier alone. A future ADR index should use unique slugs as primary keys and list numeric IDs as legacy labels.

Additional anomalies:

- `ADR-016-backend-execution-context.md` contains one newline byte and no decision content. It is an empty placeholder, not an authoritative decision. Do not invent its missing content.
- `ADR-079-bounded-multi-source-impact-and-dependency-cycles.md` has the body heading `ADR-049`. The filename and surrounding sequence indicate a title/identifier mismatch. This report records the mismatch but does not change the decision's identity or cross-references.
- `ADR-044-networkx-query-runtime-integration.md` still says fresh G9.42 validation is pending. Run `44885166907` now supplies that validation for E.8.8.2 at the pinned commit. The ADR's status text should be updated in a separate decision-record maintenance change, preserving its original decision content.
- `ADR-048-native-graph-backend-conformance.md` says GitHub native CI acceptance is pending. That remains accurate because no E.8.5/E.8.8 native workflow run was established on this commit.

## 8. M0 exit assessment

| M0 requirement | Result |
|---|---|
| Pin Stage1 source snapshot | Complete: `1ed0471832b660e8c29a946e4655e1ed981106bf` |
| Map adapter factory, projection, traversal, evidence and tool paths | Complete; limitations documented in Sections 3 and 5 |
| Distinguish implemented/tested/native-tested/repository-tested/live-used claims | Complete; no live provider acceptance claimed |
| Map existing tests to contract requirements and identify missing evidence | Complete; Section 4 |
| Inspect workflow invocation and artifact chain | Complete; Section 6 |
| Record package and platform assumptions | Complete; Section 5 |
| Reconcile ADR numbering anomalies without unsafe history edits | Complete as a classification; renumbering intentionally deferred |
| Identify unresolved semantic and integration decisions | Complete; Sections 4.1, 6.1 and 7 |

**M0 exit:** satisfied as a traceability baseline. The unresolved issues are now explicit, assigned to later milestones, and must not be represented as M0 failures or as accepted backend behavior.

## 9. Handoff to M1

M1 is the next milestone. The existing proposed specification, `AE-32C-M1-Adapter-Protocol-and-Conformance-Contract.md`, is a useful draft but is not yet an accepted protocol or implementation.

M1 must:

1. finalize the typed adapter operations for complete projection inspection and exact per-node edge-occurrence adjacency;
2. adopt explicit direction, parallel-edge, self-loop and deterministic ordering semantics, including independent expected tests for `BOTH` self-loops;
3. separate availability, API compatibility, structural conformance, native query conformance, repository conformance and approval;
4. make runtime reporting observational and distinguish one-time projection validation from query-time native access;
5. build reusable structural, behavioral, native-interaction and lifecycle/fault-injection tests;
6. prove the contract against the real NetworkX library before extending it to SciPy, igraph, graph-tool or SNAP.

Do not start SciPy native adjacency work (E.8.8.3 / M3) until the M1 contract and its NetworkX proof are accepted. Do not use a live provider experiment to compensate for missing deterministic conformance.

## 10. Change policy

- All repository writes for this milestone target `stage1/section-uuids` explicitly.
- Do not modify `main`, create a branch, rewrite history or force-push.
- Keep the canonical `SemanticGraph` authoritative.
- Keep repository graph tools read-only and bounded; no repository code execution or provider/network access in deterministic conformance.
- Distinguish pass, fail, skip, not-run and not-accepted states in every report.
- Treat this report as a traceability snapshot tied to the pinned SHA, not as a timeless statement about later commits.

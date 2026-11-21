# AE-32C M4 — python-igraph Native Adjacency Implementation Record

**Status:** ACCEPTED for the tested python-igraph 1.0.0 native adjacency and repository context path; exact scope limited to G9.42 run 44901309538  
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

## 4.1 G9.42 validation attempt and corrective review

G9.42 run [44899514712](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44899514712) checked the exact M4 implementation SHA `01983f38dd811577c43a5c35436d83ceecbb8587` on `stage1/section-uuids`, with CPython 3.11.18 and python-igraph 1.0.0. The real-library query test, native conformance test and repository context-routing test all executed and passed. The run nevertheless failed: 676/685 targeted tests passed (4 skipped, 5 failed), and 3,606/3,624 regression tests passed (12 skipped, 6 failed).

Four failures exposed an incomplete fake igraph graph lacking the documented `Graph.ecount()` method. One exposed a test monkeypatch applied to the source module rather than the imported symbol used by `capability_registry`. The remaining stale M1 assertion still expected igraph to be `not_implemented`, despite M4 correctly declaring it `implemented_unvalidated`.

The review concluded that no production adapter change was warranted. The test double now implements `ecount()`; the availability test patches the registry's actual imported symbol; and the M1 test distinguishes igraph's implemented-but-unvalidated state from graph-tool/SNAP, which remain unimplemented. Corrections:
- `0405f4f9ddd4d9142d43c5e65cf1c2ecc60955b1`
- `49a8f66489b798bc6e21a15a0bbf3b85fbe1fe89`

Detailed evidence, root-cause analysis, and rerun criteria: [M4 G9.42 Validation Failure Review — run 44899514712](AE-32C-M4-G9.42-Validation-Failure-44899514712.md).

The failed run's evidence integrity verification passed and its immutable bundle was published, but provenance catalog publication/verification correctly stopped because the validation outcome was failed. These corrections have not yet been validated by a subsequent G9.42 run. M4 remains unaccepted.

## 4.2 G9.42 rerun and second test-double correction — run 44900752438

G9.42 run [44900752438](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44900752438) tested Stage1 source SHA `932acd150bd4a0b296003b203042b372211135e1` on `stage1/section-uuids`, using CPython 3.11.18 and python-igraph 1.0.0. The independent validation-engine suite passed (53 tests). The targeted suite reported 677 passed, 4 skipped and 4 failed; full regression reported 3,608 passed, 12 skipped and 4 failed.

The remaining four failures all originated from the fake igraph `_EdgeSeq` test double. The earlier correction had added `ecount()`, but the fake still lacked integer indexing. The adapter's documented native query path obtains the edge ID from `Graph.incident()` and then reads the corresponding edge with `self.graph.es[edge_id]`. Real python-igraph supports this: its analysis guide explicitly demonstrates indexing the edge sequence (for example, `g.es[3]`) and explains that edge IDs range from zero to `ecount()-1` ([official analysis guide](https://python.igraph.org/en/latest/analysis.html)). The fake implemented iteration and attribute assignment, but not `__getitem__`, so the fake-only tests raised `TypeError: '_EdgeSeq' object is not subscriptable` before exercising their assertions.

Importantly, the real-library and repository conformance tests passed in this run:
- `test_real_optional_native_backend_query_when_installed[igraph-igraph]` — passed;
- `test_native_backend_conformance_when_library_is_installed[igraph]` — passed;
- `test_igraph_repository_conformance_routes_context_tools_through_native_adjacency` — passed.

Other real igraph projection tests in the full regression suite also passed. This evidence isolates the four failures to an incomplete test double; it does not indicate a defect in the production adapter or a reason to weaken edge-ID validation.

### Correction

The fake `_EdgeSeq` now implements integer indexing and returns an `_Edge` carrying the indexed edge's source, target and attribute access, matching the interface actually consumed by the adapter. A focused test, `test_fake_igraph_edge_sequence_supports_indexed_edge_access`, asserts that behavior directly. No production adapter code, query semantics, integrity checks, registry state or dependency constraints were changed.

Correction commit: `fc66b89428c774f45ac899c6bb154afe5a0379b2`.

### Evidence and disposition

- Targeted: 685 total; 677 passed, 4 skipped, 4 failed.
- Regression: 3,624 total; 3,608 passed, 12 skipped, 4 failed.
- python-igraph: 1.0.0 installed; real query, native conformance and repository context routing tests passed.
- Validation report SHA-256: `3043c62cdd46dedd7a97bb8bd5130e868268cfc4d8efd95afc1d270dd8750cdf`.
- Immutable evidence bundle SHA-256: `c29a10941642d4a25056615487eb21cde7647a69b3452a85bec447418a373c6a`.
- Uploaded artifact SHA-256: `c48e007582f9bd29070bf2bc20760df4c5bf76a89639e4427f31308fa2191f4d`.
- Artifact: `manual-validation-evidence-44900752438-1.zip` (ID `14705977695`).

Evidence integrity verification and immutable bundle publication passed. Provenance catalog build/verification correctly failed because the underlying test report was failed. M4 remains unaccepted until a new G9.42 run passes against the exact corrected Stage1 commit, including the newly added focused fake-interface test, real python-igraph checks, repository context conformance, full regression, evidence integrity and provenance catalog verification.

Detailed review: [M4 G9.42 Validation Failure Review — run 44900752438](AE-32C-M4-G9.42-Validation-Failure-44900752438.md).


## 4.3 Exact-commit acceptance — G9.42 run 44901309538

G9.42 run [44901309538](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44901309538) tested the exact latest Stage1 source SHA `c6d4fda93897a3b7022d28cba177fc5c453940b3` on `stage1/section-uuids`. The independent validation engine ran from `cecf208419887b70c532b57362e6933ac97f72cb`. Environment: CPython 3.11.18; python-igraph 1.0.0.

**Test results from the immutable report and JUnit XML:**
- Validation-engine tests: 53 passed.
- Targeted suite: 686 total; 682 passed, 4 skipped, 0 failed, 0 errors.
- Full regression: 3,625 total; 3,613 passed, 12 skipped, 0 failed, 0 errors.
- The focused fake edge-sequence indexing test passed.
- Real igraph query test, native conformance test and repository context-routing test executed and passed; none were skipped.
- Graph-tool and SNAP real-library tests were skipped because those libraries were not installed in the G9.42 Python interpreter. This does not affect M4 acceptance, but does mean M5 still requires a graph-tool-capable validation environment.

**Evidence chain:**
- Validation report SHA-256: `27e6714ca1a8160cb4c29078f187a1a2d071ee3e0b72a4b3bdccb1a866aec784`.
- Immutable evidence bundle SHA-256: `aabd4edc501bb2cdec425dfa3f769a3b09467172d1d361736b497293b8226d19`.
- Uploaded artifact SHA-256: `152661987cab2b0c46bb46364e7a46997003f85e61b6e92661bd3b8b9ce4c853`.
- Artifact: `manual-validation-evidence-44901309538-1.zip`, ID `14706435458`.
- Evidence integrity/outcome verification: passed.
- Immutable bundle publication: passed.
- Provenance catalog build and independent verification: passed.
- Catalog entry binds run `44901309538`, profile `G9.42`, branch `stage1/section-uuids`, tested source SHA `c6d4fda93897a3b7022d28cba177fc5c453940b3`, report digest and bundle digest.

The workflow dispatcher's top-level run SHA is the unchanged main validation-engine commit; the receipt and catalog explicitly bind the target source SHA above. Main remains unchanged. The artifact's JUnit reports independently confirm all four previously failing fake-igraph tests now pass.

**Acceptance decision:** M4 is accepted for the tested python-igraph 1.0.0 environment and the repository-backed semantic graph context path. Acceptance does not establish performance superiority, production approval for arbitrary workloads, or compatibility with untested python-igraph versions. The registry remains `implemented_unvalidated` with `production_approval: false` until the project's later promotion policy (M7) is completed. M5 may now proceed.


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
- `fc7e6e92e91764d59c5f4bca5762d073a71d2601` — require the real python-igraph version in native and repository conformance runtime evidence.

No local tests or workflows were run by the implementer. M4 is accepted for the exact tested scope. No local tests or workflows were run by the implementer.


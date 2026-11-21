# AE-32C M3 — G9.42 Validation Failure Review (Run 44895368283)

**Status:** Failure analyzed; corrective commits applied; rerun required  
**Milestone:** M3 — SciPy CSR/CSC native adjacency  
**Workflow:** [G9.42 manual validation run 44895368283](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44895368283)  
**Target branch:** `stage1/section-uuids`  
**Target source SHA:** `78ece9ccdab4b4597930ba315d4c019175089119`  
**Python:** 3.11.18  
**Validation engine SHA:** `cecf208419887b70c532b57362e6933ac97f72cb`

The dispatcher itself was triggered from `main`, but its log explicitly checked out `stage1/section-uuids` and recorded the target source SHA above. This run therefore validates the Stage1 snapshot, not the main source tree.

---

## 1. Outcome

| Evidence | Result |
|---|---:|
| Validation-engine unit tests | 53 passed |
| Targeted tests | 682 total: 674 passed, 6 skipped, 2 failed |
| Full regression | 3,621 total: 3,604 passed, 14 skipped, 3 failed |
| Evidence digest/checksum verification | Passed |
| Immutable evidence bundle | Published and verified |
| Provenance catalog | Correctly blocked because validation status was failed |

The validation report SHA-256 is `2be464d33213dbd8ae9217bded06a922b70ef579fdcf0d4234e2b6420931d5e7`. The immutable bundle SHA-256 is `b954bc0ec3242198231df1d883826b42f6014b8de9772ce60be7e8ca0f9f02eb`. The uploaded workflow artifact SHA-256 is `387a6e40a4b3637d02c24ee5ea9a762fe49ea27311a001bd482174e160471f1c`.

The regression log reports 149 warnings. These did not cause the failures.

## 2. Failure analysis

### 2.1 Reference/native parity mismatch for BOTH with a self-loop

Failing test:

`tests/semantic_graph/test_e83_multi_backend_traversal.py::test_scipy_both_direction_returns_self_loop_occurrence_once`

The SciPy adapter's `iter_adjacent_edge_occurrences(..., BOTH)` correctly unions outgoing and incoming local sparse adjacency by canonical occurrence ID. A self-loop is consequently returned once.

The mismatch was in the reference traversal's input normalization. The test supplied the valid string `"both"`. The native adapter normalized that string to `TraversalDirection.BOTH` inside its candidate-selection override, but `GraphTraversalEngine.walk()` retained the raw string. The reference candidate selector used an identity check (`direction is TraversalDirection.BOTH`) when excluding the duplicate incoming view of a self-loop. A raw string compares equal to the string enum but is not the same enum object, so the reference path included the self-loop twice.

This is an oracle-boundary defect, not evidence that CSR or CSC returned the wrong sparse coordinate.

**Correction:** normalize and validate `direction` once at the public `GraphTraversalEngine.walk()` boundary. The reference and native implementations now receive the same enum value. A reference-specific test asserts the independent expected contract: one self-loop step and two total incident edge occurrences in the adversarial fixture.

### 2.2 SciPy repository context telemetry did not expose native adjacency usage

Failing test:

`tests/semantic_graph/test_e83_multi_backend_traversal.py::test_scipy_repository_conformance_routes_context_tools_through_native_adjacency`

The context tools already called `SemanticGraphAnalysisService.analyze()`, and the selected SciPy traversal engine performed native CSR/CSC adjacency access. However, `RepositoryEvidenceTools._context_edges()` obtains per-operation native counters from the graph-analysis result metadata field `backend_native_query_metrics`.

The NetworkX traversal engine supplies that field from its per-query native counters. `NativeAdapterGraphTraversalEngine.result_metadata()` did not. The context tool therefore recorded zero native lookups despite the SciPy traversal path being invoked. This is an observability/interface mismatch: the test correctly refused to infer native routing from backend selection alone.

**Correction:** the native adapter traversal engine now exposes SciPy's per-walk deltas for `native_adjacency_lookups` and `native_edge_occurrences_read` through `backend_native_query_metrics`, together with the explicit mode `scipy_csr_csc_adjacency`. The mode is also exposed in the runtime report. Counters are deltas for the most recent walk, not cumulative totals misrepresented as a single operation.

### 2.3 Repository conformance report mislabeled SciPy as NetworkX

The repository conformance runner hard-coded `networkx_native_successor_predecessor_adjacency` for all three context-tool report entries. This was inherited from the M2 NetworkX-only conformance contract and was not appropriate once the runner accepted a backend parameter.

Although the failing assertion surfaced first through missing telemetry, this was a separate report correctness defect: a SciPy report must not claim that NetworkX served its context operations.

**Correction:** the runner now obtains the execution-mode label from the selected backend's runtime report and uses that value for direct trace, nested workflow context and direct workflow context. SciPy reports `scipy_csr_csc_adjacency`. Native adapters without implemented local adjacency explicitly report `canonical_python_adjacency_fallback`, avoiding a false native-execution claim.

### 2.4 Stale M1 capability-registry expectation

Failing test:

`tests/semantic_graph/test_m1_adapter_protocol_networkx.py::test_registry_separates_discovery_from_conformance_and_approval`

The test still expected SciPy's `native_adjacency_implementation` to be `not_implemented`. M3 had deliberately changed the registry to `implemented_unvalidated`, while keeping conformance at `not_run` and production approval false.

**Correction:** the test now asserts the M3 state for SciPy and retains `not_implemented` for igraph, graph-tool and SNAP. No acceptance state is promoted by this change.

---

## 3. Corrective commits

All changes below target `stage1/section-uuids`; no local tests or workflows were run by the implementer.

| Commit | Change |
|---|---|
| `946faa6e3a9357b24f5e08c4ba35f02d95590720` | Normalize traversal direction in the reference engine |
| `d8f4023973d4b923bbd9811e51cffd9c24fa524` | Add per-query SciPy native adjacency metrics to result metadata |
| `99bf99b25a63f329fd8094a475e9c0397fcdf34d` | Correct stale M1 registry expectation |
| `71230791382d3d1fdbed20c376dd3e46186ae34e` | Add reference self-loop contract and context telemetry assertions |
| `d7af14c111c109584e6a0098e2e05b59701fc166` | Expose actual context execution mode in runtime reporting |
| `5cde812d63db340c14f28c0b50dff44bab551524` | Remove hard-coded NetworkX context-mode labels from conformance report |
| `32f20bda4e6535ac90a9ad165a2a47f95d622b81` | Assert all three repository context report entries identify the SciPy mode |

These are implementation corrections, not validation results. The new tests have not yet been executed against the corrected source.

## 4. Technical review of the SciPy projection

The CSR/CSC design remains appropriate for this directed sparse-adjacency workload:

- CSR row storage supports local outgoing adjacency.
- CSC column storage supports local incoming adjacency.
- The side-channel occurrence mapping preserves parallel edge identity and semantic payloads that a collapsed sparse coordinate cannot carry independently.
- The `BOTH` result is a union by occurrence ID, so a self-loop is not duplicated.
- Full native projection enumeration remains confined to the construction-time audit; runtime reporting uses cached projection counts and counters.

The official SciPy API documents CSR row segments through `indptr` and `indices`, and CSC column segments through the analogous compressed-column arrays. See the [CSR matrix reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csr_matrix.html) and [CSC matrix reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csc_matrix.html).

This review does not identify a defect in the sparse storage layout itself. It does identify that the original implementation was incomplete at two integration boundaries: canonical traversal input normalization and the per-query metadata contract used by repository context tools. Those boundaries are now corrected in source but remain unverified until a rerun.

## 5. Acceptance status and next action

**M3 remains implemented but unvalidated.** The failed run must not be treated as a SciPy conformance pass. The evidence integrity and immutable bundle checks passing only establish that the failed run's evidence was preserved correctly.

Request a new G9.42 run against the latest `stage1/section-uuids` head. Acceptance requires:

1. the SciPy BOTH/self-loop parity test to pass;
2. repository context conformance to show positive SciPy native adjacency lookup and occurrence-read counters for direct trace, nested workflow context and direct workflow context;
3. all three report entries to identify `scipy_csr_csc_adjacency`;
4. the stale M1 registry assertion to pass;
5. targeted and full regression to pass, with skips stated;
6. evidence integrity verification and provenance catalog build/verification to pass.

Do not begin M4 or mark SciPy conformant until that exact-commit evidence exists.

# AE-32C M4 — G9.42 Validation Failure Review (run 44900752438)

**Disposition:** Four test-double failures diagnosed; corrective change committed; exact-commit rerun required  
**Target branch:** `stage1/section-uuids` only  
**Tested source SHA:** `932acd150bd4a0b296003b203042b372211135e1`  
**Workflow:** [Manual Validation Dispatcher run 44900752438](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44900752438)  
**Job:** [136835933115 — Validate selected branch using main engine](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44900752438/job/136835933115)  
**Profile:** G9.42; CPython 3.11.18; python-igraph 1.0.0

## 1. Executive result

The run failed because four tests using the fake igraph implementation reached an edge-sequence operation that the fake did not implement. The real python-igraph tests and repository-backed conformance test passed. This is a test-double fidelity defect, not evidence of a production adapter defect.

No production behavior was weakened or changed. The fake edge sequence now implements integer indexing, and a focused test verifies that contract. Correction commit: `fc66b89428c774f45ac899c6bb154afe5a0379b2`.

M4 remains unaccepted until G9.42 passes against the corrected Stage1 commit and the evidence/provenance gates complete.

## 2. Run and evidence identity

| Item | Observed value |
|---|---|
| Run ID / attempt | `44900752438` / `1` |
| Target branch | `stage1/section-uuids` |
| Tested source commit | `932acd150bd4a0b296003b203042b372211135e1` |
| Dispatcher engine commit | `cecf208419887b70c532b57362e6933ac97f72cb` |
| Python | `3.11.18` |
| python-igraph | `1.0.0` |
| Validation-engine tests | 53 passed |
| Targeted tests | 685 total: 677 passed, 4 skipped, 4 failed |
| Regression tests | 3,624 total: 3,608 passed, 12 skipped, 4 failed |
| Validation report SHA-256 | `3043c62cdd46dedd7a97bb8bd5130e868268cfc4d8efd95afc1d270dd8750cdf` |
| Immutable evidence bundle SHA-256 | `c29a10941642d4a25056615487eb21cde7647a69b3452a85bec447418a373c6a` |
| Uploaded artifact SHA-256 | `c48e007582f9bd29070bf2bc20760df4c5bf76a89639e4427f31308fa2191f4d` |
| Artifact | `manual-validation-evidence-44900752438-1.zip`, ID `14705977695` |

The dispatcher itself ran from the unchanged main validation engine SHA. It checked out the requested Stage1 branch for the source under test. No main-branch write was made.

## 3. Failure inventory

All four failures are in `tests/semantic_graph/test_e83_multi_backend_traversal.py` and have the same exception:

```text
TypeError: '_EdgeSeq' object is not subscriptable
```

The failed tests are:

1. `test_optional_native_adapter_is_used_by_live_query_path[igraph]`
2. `test_igraph_native_incident_edge_ids_preserve_occurrences_and_avoid_full_scans`
3. `test_native_projection_mutation_fails_closed`
4. `test_e85_conformance_runner_contract_with_adapter_test_double[igraph]`

The traceback identifies the production adapter's indexed edge lookup:

```python
edge = self.graph.es[edge_id]
```

The test double `_EdgeSeq` had `__setitem__` and `__iter__`, but no `__getitem__`. Thus it could be populated and iterated during projection construction/audit, but could not emulate the adapter's query-time retrieval of an edge by the native edge ID.

## 4. Technical review

### 4.1 The production access pattern is consistent with python-igraph

The adapter first asks `Graph.incident(vertex_id, mode="out"|"in")` for local native edge IDs. It validates each ID against `Graph.ecount()`, then resolves that ID through `Graph.es[edge_id]` to read the exact edge object and its semantic occurrence/payload attributes.

This is the appropriate occurrence-preserving design: the adapter receives edge IDs rather than only neighboring vertex IDs, so parallel edges remain individually addressable. The official python-igraph analysis guide documents edge IDs in the range zero through `ecount()-1`, and explicitly demonstrates indexing the edge sequence (e.g. `g.es[3]`): [python-igraph 1.0.0 analysis guide](https://python.igraph.org/en/latest/analysis.html). The Graph API also documents `ecount()` and the incident-edge API: [python-igraph Graph API](https://igraph.org/python/api/latest/igraph.Graph.html).

### 4.2 Why the previous correction was incomplete

The preceding run 44899514712 revealed that the fake graph lacked `ecount()`. That method was added, but the fake edge sequence still did not satisfy the next interface operation. This is a classic partial test-double implementation: one missing method was fixed while the next method in the same production call chain remained unmodeled.

The correct fix is to bring the fake up to the subset of the real library API that production code consumes. It would be incorrect to change production code to avoid `Graph.es[edge_id]`, skip edge identity validation, or convert the native edge IDs into neighbor-only lookups merely to satisfy the fake.

### 4.3 Real-library and repository evidence

The XML reports establish that the following tests executed and passed rather than being skipped:

- `test_real_optional_native_backend_query_when_installed[igraph-igraph]`;
- `test_native_backend_conformance_when_library_is_installed[igraph]`;
- `test_igraph_repository_conformance_routes_context_tools_through_native_adjacency`.

The repository test verified context-tool routing through the igraph native incident-edge execution mode. Additional igraph projection tests in the full regression suite also passed. These results strongly localize the four failures to the fake edge sequence. They do not by themselves establish overall M4 acceptance because the complete targeted and regression runs failed.

## 5. Corrective implementation

Updated `_EdgeSeq` in `tests/semantic_graph/test_e83_multi_backend_traversal.py`:

- implement `__getitem__(index)`;
- resolve the indexed source/target pair;
- return the corresponding `_Edge` instance, retaining edge attributes through the existing `_Edge.__getitem__`.

Added `test_fake_igraph_edge_sequence_supports_indexed_edge_access`, which builds a one-edge fake graph and independently checks indexed edge source, target and attribute access.

Commit: `fc66b89428c774f45ac899c6bb154afe5a0379b2`.

Scope is deliberately test-only. No changes were made to `IGraphAdapter`, edge-ID validation, semantic occurrence mapping, traversal ordering, parity checks, native telemetry, dependency versions or registry acceptance state.

## 6. Evidence pipeline disposition

- Evidence integrity verification: passed.
- Immutable evidence bundle publication: passed.
- Provenance catalog build: blocked because the validation outcome was failed.
- Independent provenance catalog verification: blocked for the same reason.

This is the expected fail-closed behavior. The catalog must not represent a failed test run as an accepted validation record.

## 7. Required rerun / acceptance gate

Run G9.42 on the latest `stage1/section-uuids` head. Acceptance requires:

1. The new focused fake edge-sequence test passes.
2. All four previously failing fake-igraph tests pass.
3. Real python-igraph 1.0.0 query and native conformance tests execute and pass, not skip.
4. Repository context conformance continues to report `igraph_incident_edge_ids`, positive native adjacency/edge-occurrence counters, zero parity failures and verified source follow-through.
5. Targeted and full regression suites have zero failures/errors.
6. Evidence integrity, immutable bundle publication and provenance catalog build/verification all pass for the exact tested Stage1 SHA.

Until then, keep igraph at `implemented_unvalidated`, production approval false, and do not start M5. No local tests or workflows were run as part of this correction; validation remains the user's G9.42 workflow.

## 8. References

- [python-igraph 1.0.0 analysis guide](https://python.igraph.org/en/latest/analysis.html) — documents edge ID ranges, `ecount()`, and indexed access through `g.es[edge_id]`.
- [python-igraph Graph API](https://igraph.org/python/api/latest/igraph.Graph.html) — documents `Graph.ecount()` and `Graph.incident()`.

# AE-32C M4 — G9.42 Validation Failure Review (run 44899514712)

**Status:** Failure analyzed; test-harness corrections committed; exact-commit G9.42 rerun required  
**Milestone:** M4 — python-igraph native adjacency  
**Target branch:** `stage1/section-uuids` only  
**Workflow:** [Manual Validation Dispatcher run 44899514712](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44899514712)  
**Tested source SHA:** `01983f38dd811577c43a5c35436d83ceecbb8587`  
**Validation engine SHA:** `cecf208419887b70c532b57362e6933ac97f72cb`  
**Profile / runtime:** G9.42 / CPython 3.11.18  
**Installed python-igraph:** `1.0.0`

## 1. Outcome

The dispatcher checked out the intended Stage1 branch and exact M4 implementation snapshot. The validation failed because of five targeted failures and six regression failures (the regression suite includes the targeted test files).

| Suite | Tests | Passed | Skipped | Failed | Errors |
|---|---:|---:|---:|---:|---:|
| Targeted | 685 | 676 | 4 | 5 | 0 |
| Full regression | 3,624 | 3,606 | 12 | 6 | 0 |
| Validation-engine tests | 53 | 53 | 0 | 0 | 0 |

The workflow's evidence integrity check succeeded and the immutable evidence bundle was published. Provenance catalog publication and verification correctly failed because the validation result was not passed.

Evidence:
- Artifact: `manual-validation-evidence-44899514712-1.zip`
- Artifact SHA-256: `84d2b230f33d72ef72ec654bce58099d65ef8c7e11f92396bfcfbb2855e4b362`
- Validation report SHA-256: `a7111bdeda65c1d0309cb493a637d9517dfb06bcea233d956571ab2a8203d14d`
- Published bundle SHA-256: `06f1d754b808fd056f43592cdff37619228a9c36ff81ccc754fd3f1b320b9532`

The report identifies the tested target branch and source SHA. The dispatcher itself runs from `main`; that is the validation-engine checkout, not the Stage1 source under test.

## 2. Important positive evidence

The dependency correction worked. The job log shows that G9.42 installed `igraph==1.0.0` from `source/requirements.txt`.

The following real-library and repository-backed tests executed and passed (they were not skipped):

- `test_real_optional_native_backend_query_when_installed[igraph-igraph]`
- `test_native_backend_conformance_when_library_is_installed[igraph]`
- `test_igraph_repository_conformance_routes_context_tools_through_native_adjacency`

Thus the run establishes that the real python-igraph 1.0.0 API was importable and that the real-library query, native conformance, and repository context-routing checks passed. This is meaningful M4 evidence, but it is not acceptance because other tests failed.

## 3. Failure analysis

### 3.1 Fake igraph omitted the documented `Graph.ecount()` API

Four failures had the same root cause:

- `test_optional_native_adapter_is_used_by_live_query_path[igraph]`
- `test_igraph_native_incident_edge_ids_preserve_occurrences_and_avoid_full_scans`
- `test_native_projection_mutation_fails_closed`
- `test_e85_conformance_runner_contract_with_adapter_test_double[igraph]`

The adapter checks that every incident edge ID is an integer in the valid range:

```python
0 <= edge_id < self.graph.ecount()
```

That check is appropriate for python-igraph. The official API documents `Graph.ecount()` as the edge count, and graph edge IDs are numbered from zero to `ecount()-1`. The fake `_FakeIGraph` test double implemented `incident()`, `add_edges()`, and edge sequences, but omitted `ecount()`. The failure is therefore a test-double contract defect, not evidence of an incompatibility in the production adapter.

**Correction:** implement `ecount()` in `_FakeIGraph`, returning the number of stored edge pairs. Keep the production adapter's bounds check; do not weaken native edge-ID validation to accommodate an incomplete fake.

### 3.2 Explicit-unavailable-backend test patched the wrong symbol

Failure:
- `test_explicit_backend_selection_never_silently_falls_back`

The test monkeypatched `optional_backend_support.backend_available`. However, `capability_registry.py` imports that function directly at module import time:

```python
from ...optional_backend_support import backend_available
```

`create_default_registry()` subsequently calls the already-imported symbol in `capability_registry`. Replacing the original function in `optional_backend_support` does not replace the bound name in `capability_registry`; the test was not actually simulating an unavailable igraph dependency.

**Correction:** patch `capability_registry.backend_available`, the symbol used by registry construction. Keep the production fail-closed selection behavior unchanged.

### 3.3 M1 registry test retained a stale pre-M4 expectation

Failure:
- `test_registry_separates_discovery_from_conformance_and_approval`

The M1 test expected igraph native adjacency implementation state to remain `not_implemented`. M4 intentionally changed that state to `implemented_unvalidated`, while leaving conformance `not_run` and production approval `false`.

**Correction:** assert the M4 state for igraph and preserve the `not_implemented` expectation for graph-tool and SNAP. This updates the test's milestone knowledge without promoting igraph to accepted or production-approved status.

## 4. Technical review and disposition

No production adapter change is justified by these six failures:

- `Graph.ecount()` is a documented python-igraph API, so the fake should model it.
- The availability test had a monkeypatch-target error; the registry's production behavior is not disproved.
- The registry assertion was obsolete after the M4 implementation state was introduced.

The real python-igraph 1.0.0 test and repository conformance test both passed, providing independent evidence that the production adapter's use of incident edge IDs and edge counts is compatible with the installed library. The correction is deliberately limited to tests; no production semantics, native adjacency behavior, backend capability, or approval state are changed.

## 5. Corrective commits

- `0405f4f9ddd4d9142d43c5e65cf1c2ecc60955b1` — add `ecount()` to the fake igraph graph and patch the availability symbol actually consulted by registry construction.
- `49a8f66489b798bc6e21a15a0bbf3b85fbe1fe89` — update the M1 registry test to distinguish implemented-but-unvalidated igraph from still-unimplemented graph-tool and SNAP.

These are test-only corrections. No local tests or workflows were run by the implementer.

## 6. Required rerun and acceptance boundary

Run G9.42 against the latest `stage1/section-uuids` head after these corrections. Acceptance requires:

1. All fake-adapter tests pass, including the E.8.3 native incident-edge contract and E.8.5 test-double runner.
2. The explicit unavailable-backend test demonstrates fail-closed selection using the correctly patched registry dependency.
3. The M1 registry test confirms igraph remains `implemented_unvalidated`, conformance `not_run`, and production approval false.
4. Real python-igraph 1.0.0 tests execute rather than skip and pass.
5. Repository-backed context operations use `igraph_incident_edge_ids`, report positive native adjacency/occurrence metrics, and preserve source follow-through and reference parity.
6. Targeted and full regression suites pass.
7. Evidence integrity, immutable bundle publication, provenance catalog build, and independent catalog verification all pass.

Until that exact-commit run passes, M4 remains implemented but unaccepted. Do not begin M5 and do not promote igraph to production-approved.

## 7. Technical references

- python-igraph Graph API: `Graph.ecount()` counts edges; incident-edge APIs are documented in the [Graph API reference](https://python.igraph.org/en/latest/api/igraph.Graph.html).
- python-igraph analysis guide: edge IDs range from zero to `ecount()-1`, and `Graph.incident()` returns incident edge IDs: [Vertices, edges and incidence](https://python.igraph.org/en/main/analysis.html).

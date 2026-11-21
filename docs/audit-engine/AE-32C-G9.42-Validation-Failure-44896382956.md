# AE-32C — G9.42 Validation Failure Review (Run 44896382956)

**Status:** Single stale test expectation corrected; G9.42 rerun required  
**Milestone under validation:** M3 — SciPy native sparse adjacency  
**Workflow:** [Manual Validation Dispatcher run 44896382956](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44896382956)  
**Target branch:** `stage1/section-uuids`  
**Target source SHA:** `60192a96dafef2e8f1381719950578d061114c2f`  
**Validation engine SHA:** `cecf208419887b70c532b57362e6933ac97f72cb`  
**Profile:** G9.42; profile SHA-256 `db44990752010b9975464dd49c2aad4fdc4f44525556831106591a474ad3a193`  
**Python:** 3.11.18

## 1. Run outcome

The dispatcher was triggered from `main`, but the evidence report confirms that the requested development branch was `stage1/section-uuids` at the target SHA above. The run therefore evaluated the intended Stage1 snapshot.

| Evidence | Result |
|---|---:|
| Validation-engine unit tests | 53 passed |
| Targeted suite | 683 total: 676 passed, 6 skipped, 1 failed |
| Full regression | 3,622 total: 3,607 passed, 14 skipped, 1 failed |
| Detached evidence digest/checksum verification | Passed |
| Immutable evidence bundle publication | Passed |
| Provenance catalog build | Blocked by failed validation status |
| Independent provenance catalog verification | Blocked because no passing catalog was produced |

The validation report SHA-256 is `3d95b018f53206c42b45a9da96738cb4b8c451884a7da0519ed71774cf534f33`. The immutable bundle SHA-256 is `2c172cd4c30ae98c110842c9ccc6dbf3ced8ec381b3d57612b1035c8497e57a2`. The uploaded workflow artifact SHA-256 is `5f5fc42094b55caa1612aa67c1dcd84efd85209c663f7555a3e549652be1fb1c`.

The regression log reports 149 warnings. They were not the cause of the failure.

## 2. Exact failure

Both the targeted suite and full regression failed on the same test:

`tests/semantic_graph/test_e88_networkx_repository_backend.py::test_repository_conformance_runner_requires_native_context_tool_routing`

The assertion expected:

`networkx_native_successor_predecessor_adjacency`

The actual conformance report returned:

`networkx_successor_predecessor_adjacency`

This is a stale test expectation, not a failed native adjacency operation.

The implementation's NetworkX adapter traverses the native `MultiDiGraph` successor and predecessor adjacency structures. Its runtime report explicitly identifies the mode as `networkx_successor_predecessor_adjacency`. The direct adapter test independently asserts that exact value, and it also monkeypatches `MultiDiGraph.edges` to fail if a query attempts a full edge scan. The conformance runner obtains the mode from the selected backend's runtime report rather than inventing a separate label.

The old `_native_` substring was retained in the repository-level assertion after the reporting label had been standardized. Updating production code merely to satisfy that stale string would create an unnecessary second naming convention and risk misrepresenting the established runtime contract.

## 3. M3 interpretation

This run is materially better than the previous M3 run (44895368283): the previous two SciPy-related integration failures and stale M1 registry assertion did not recur. The targeted suite now has only the unrelated NetworkX label assertion failing. The SciPy implementation-specific assertions therefore passed within this run's targeted suite, including the checks added for native CSR/CSC query telemetry and repository context execution mode.

However, this is not yet M3 acceptance. A failed full regression remains a failed validation, and the provenance catalog was correctly not finalized as a passing validation artifact.

The 6 targeted skips concern optional igraph, graph-tool and SNAP native libraries not installed in this interpreter. They do not indicate SciPy skips. The full-regression skips also include environment-dependent SNAP/Python 3.9, pyoxigraph and pdflatex cases; see the attached run logs for their exact reasons.

## 4. Corrective change

The sole failing assertion was corrected in:

`tests/semantic_graph/test_e88_networkx_repository_backend.py`

Both the trace-context and direct workflow-context report expectations now use the actual runtime mode:

`networkx_successor_predecessor_adjacency`

No production traversal implementation was changed. No backend acceptance state was promoted.

Corrective commit:

`4dc1a40681dab18b55f4fc4af0d45adbd21c8c83`

The change is committed to `stage1/section-uuids`. No local test execution was performed by the implementer.

## 5. Required rerun and acceptance

Run G9.42 against the latest `stage1/section-uuids` head.

Acceptance requires:

1. the corrected NetworkX context-mode assertion to pass;
2. the complete targeted suite to pass, with skips reported;
3. full regression to pass, with skips reported;
4. evidence digest/checksum verification to pass;
5. immutable evidence publication to pass;
6. provenance catalog construction and independent verification to complete successfully;
7. the validation report to identify the exact corrected Stage1 commit.

M3 remains implemented but unvalidated until that exact-commit rerun succeeds. Do not begin M4 or mark SciPy production-approved based on this failed run.

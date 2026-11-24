# AE-32C M7.4 — Initial Task Assessment Validation Record

**Status:** Initial STRUCTURAL / DEPENDENCY / PATH / IMPACT task-level acceptance passed across all five backend environments; formal suitability verdicts remain pending.  
**Target branch:** `stage1/section-uuids`  
**Exact source commit:** `942b54f8948286b4727ca208fdfa553e019437b9`  
**Parent commit:** `e6a985d44cc97521f730fc717f35fd4a0d9bf4cd`  
**Workflow:** [AE-32C Native Graph Backend Conformance (E.8.5 / E.8.8), run 45381213888](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45381213888)  
**Event / attempt:** push / 1  
**Validation date:** 2026-11-24  
**Authority:** `production_approval=false`; no ranking, winner, selector activation or runtime promotion.

---

## 1. Change under validation

Commit `942b54f8948286b4727ca208fdfa553e019437b9` adds the M7.4 test module:

- `tests/semantic_graph/test_m74_task_suitability_acceptance.py`

and integrates it into:

- `validation/profiles/G9.42.yaml`;
- `.github/workflows/e85-native-graph-backend-conformance.yml`.

No analyzer, adapter, selector or other application runtime implementation was modified in this commit. The tests exercise the existing public `SemanticGraphAnalysisService` path.

## 2. Exact test results

Each job selected one backend using `AE32C_M74_BACKEND`. The module is parametrized across all five backends; consequently the other four backend partitions are deliberately skipped in each job.

| Backend | Workflow job ID | Pytest result |
|---|---:|---:|
| NetworkX | `138400416078` | 7 passed, 28 skipped |
| SciPy | `138400415869` | 7 passed, 28 skipped |
| python-igraph | `138400415873` | 7 passed, 28 skipped |
| graph-tool | `138400416016` | 7 passed, 28 skipped |
| SNAP isolated worker | `138400415896` | 7 passed, 28 skipped |

**Aggregate:** 35 passing backend-specific test executions across the five environments. The 140 skips are expected selections of the four non-targeted backend partitions; they are not failures.

The E.8.5/E.8.8 backend jobs all concluded `success`. Aggregate summary job `138400786827` also concluded `success`. Individual M7.4 pytest results were inspected in the job logs; the overall workflow conclusion was not used as a substitute for inspecting the test step.

## 3. Task contract exercised

The test fixture is intentionally small and diagnostic: five nodes and seven edge occurrences. It contains two parallel edge occurrences with the same endpoints and relation label but distinct metadata, one decoy relation excluded by query filters, a transitive dependency chain, an incoming edge and a self-loop.

### 3.1 STRUCTURAL

Verified through the public service:

- depth-one neighborhood and explicit relation filtering;
- preservation of both parallel edge occurrences and their distinct evidence provenance;
- incoming and bidirectional traversal behavior;
- a bidirectional self-loop is emitted once;
- independent expected node/edge assertions and canonical graph immutability.

### 3.2 DEPENDENCY

Verified through the public service:

- direct and transitive dependency discovery with `IMPORTS` and `DEPENDS_ON`;
- exclusion of the deliberately present `USES` edge;
- exact expected nodes, observations and evidence;
- an exhausted traversal-step budget returns `INCOMPLETE` with truncation metadata, rather than implying a complete traversal.

### 3.3 PATH

Verified through the public service:

- bounded path from A to C through A–B–D–C;
- path-step observations and associated evidence;
- exclusion of a direct A–C edge outside the selected relation vocabulary;
- step-budget exhaustion returns `INCOMPLETE` and does not return a fabricated partial path as complete.

### 3.4 Cross-backend assertions

For each tested operation/backend pair, tests compare semantic result fields against the reference service, assert the backend's declared native query mode, require nonzero native adjacency and edge-occurrence telemetry, require per-query reference parity, assert zero query failures, and verify that the canonical `SemanticGraph` has not changed.

This provides evidence that the task route invoked the selected native backend under the tested conditions. It is not a general proof of all possible native API paths or graph shapes.

## 4. SNAP execution identity

The SNAP job successfully built the isolated worker image and recorded the run-time Docker image ID:

`sha256:f94d166165f7676f031bb476a79b0c7e112ef65f0f9c4ef5027844891f1eb4b3`

The M7.4 test requires the SNAP environment to provide an image ID with a `sha256:` prefix. The run's backend report also contains the same `container_image_id`.

This closes the missing image-identity field for this execution. It does not close the separate worker-request issue: `stdout.readline()` still has no per-request response deadline. A stalled request may therefore remain unbounded even though the workflow job has an outer job timeout. Explicit timeout, termination and recovery tests are still required.

## 5. Existing E.8.5 / E.8.8 artifacts

The same run uploaded native conformance evidence packages. Their archive digests are recorded below. These artifacts support the E.8.5/E.8.8 synthetic and repository-backed conformance scope; they are not standalone M7.4 pytest-result artifacts. The M7.4 test counts above come from the corresponding workflow job logs.

| Backend | Artifact ID | SHA-256 archive digest |
|---|---:|---|
| NetworkX | `14913303335` | `385fccc2fe626c67c63e7d4d6880586379a366f158c45644d1a630974c5dcb5b` |
| SciPy | `14914566399` | `646741864aaf875e1ad6b1067c3d21b45eefa951e4e914295411bd15bac08947` |
| python-igraph | `14914321483` | `289039c42c5c7cf414be3f77b0b6879d78c60e63c7ac24c16e1689d40cbb52ec` |
| graph-tool | `14914711308` | `40caa0d35bebffc897d338070121692e983b663662e4ce0ff9acfcd84204114c` |
| SNAP isolated worker | `14914815230` | `41e40a7ae601cf44b1fffa0f7bd80285b39a644304549c968c4f5f4804cfdea9` |

## 6. What this run does not establish

This run does not establish any final suitability verdict for the 20 task/backend pairs (four public tasks across five backend options).

1. **Workload representativeness:** the M7.4 fixture is a focused five-node synthetic graph. It is not a representative or scale-complete test of the five M7.2 workload families, real repository evidence density, production graph sizes, memory pressure or throughput.
2. **PATH domain interpretation:** generic graph path/evidence traversal is tested. Claim-to-evidence reconstruction, locator correctness and source-content follow-through remain distinct requirements.
3. **IMPACT:** the follow-up run now tests multi-source budget allocation, deterministic candidate merging, per-source attribution, ownership/evidence resolution, cycle evidence and incomplete-result reporting. The test fixture remains small and synthetic; the canonical-graph cycle scan is not a native backend SCC operation, and representative workload/scale evidence remains open.
4. **SNAP lifecycle:** the Stage1 adapter now enforces request deadlines and attempts container-ID-based forced removal. The adapter test step passes on `6b32b0b`; those tests use mocked process/Docker behavior, so real stalled-container cleanup is not yet demonstrated. The latest E.8.8 step remains in progress.
5. **Selector policy:** this change does not alter the generic first-match selection behavior or require task-specific acceptance states at selection time.
6. **G9.42:** the new test file was added to the G9.42 profile, but G9.42 was not dispatched against this commit. The passing evidence here comes from run 45381213888.
7. **Promotion:** no library is declared universally or comparatively superior; no runtime selection policy is activated.

## 7. Bounded conclusion and next gates

**Supported statement:** At source SHA `942b54f8948286b4727ca208fdfa553e019437b9`, the existing public STRUCTURAL, DEPENDENCY and PATH service routes passed the initial synthetic semantic-acceptance test suite in each of the five configured backend environments. Each tested route reported its expected native query mode and positive local-adjacency telemetry, matched the reference service on asserted semantic output, and left the canonical graph unchanged.

**Not supported:** a final suitable/conditionally suitable/not suitable decision, workload-wide task suitability, claim-to-evidence correctness, full IMPACT suitability, bounded SNAP request operation, selector authorization, production approval.

Next gates are to expand task-specific workload and evidence records for all four public tasks, complete current SNAP E.8.8 evidence, add a live Docker stalled-container cleanup test, resolve selector policy separately, and run G9.42 against an exact Stage1 commit when dispatch capability is available.

`production_approval=false` remains invariant.



## 8. IMPACT follow-up validation — 2026-11-24

**Corrected test source:** `ff6fe8226d6417b0832a17b8bed397217f72a303`  
**Previous test commit:** `b6b81b60753cf36334281f19c3ff64aea5abe7b9`  
**Workflow:** [AE-32C Native Graph Backend Conformance run 45382782600](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45382782600)  
**Final result:** success, attempt 1; five backend jobs and aggregate summary succeeded.

The corrected M7.4 module reported the following in each backend environment:

| Backend | M7.4 result |
|---|---:|
| NetworkX | 11 passed, 44 intentionally skipped |
| SciPy | 11 passed, 44 intentionally skipped |
| python-igraph | 11 passed, 44 intentionally skipped |
| graph-tool | 11 passed, 44 intentionally skipped |
| SNAP isolated worker | 11 passed, 44 intentionally skipped |

The 44 skips per job are the four backend partitions not selected by that job. Across the five jobs, the complete module therefore produced 55 passing backend-specific test executions and 220 expected skips. The run also completed the existing E.8.5/E.8.8 conformance jobs and aggregate summary successfully.

### 8.1 Additional IMPACT behaviors covered

The four IMPACT test cases per backend verify multi-source shared-candidate merging and per-source paths, source-order deterministic results, depth-one ownership evidence, test/workflow/symbol candidate categorization, cycle evidence, global per-source budget allocation and truncation, cycle-scan-limit incompleteness, and rejection of duplicate or more-than-25 changed sources.

The test suite checks that the selected backend executes the ownership and reverse-dependency traversal calls, that each such query matches the reference traversal, that native adjacency and edge-occurrence telemetry are positive, and that no backend query failures or parity failures occur. It also checks that the canonical semantic graph is unchanged.

### 8.2 Test-oracle correction

The preceding run `45382609610` at commit `b6b81b60753cf36334281f19c3ff64aea5abe7b9` failed on one over-broad test expectation: it required `MEMBER_OF` in file-source ownership evidence even though the file analyzer resolves ownership only one hop from the changed file. `MEMBER_OF` linked a symbol discovered on that first hop to its module on a second hop. The correction removed that second-hop expectation and retained the direct `IMPLEMENTS`, `IMPLEMENTED_BY` and `DEFINES` assertions. This was a test-oracle correction; no runtime source was modified. The corrected exact-source run `45382782600` then passed in all five environments.

### 8.3 IMPACT execution boundary

The IMPACT analyzer's source-ownership and reverse-dependency traversal calls use the configured backend. Its cycle-detection sub-operation does not: `_dependency_cycles` reads and sorts the canonical graph's complete edge collection (subject to the global 50,000-edge limit), then induces the impacted-node subgraph and computes strongly connected components. The tests verify cycle output/evidence and fail-closed behavior when the scan limit is exceeded, but do not establish native backend SCC capability or cycle-scan performance. This must remain explicit in any later task/backend record.

The SNAP worker image ID for this follow-up run was `sha256:8aa923b1de4d7b2ca7301cb27556178e35e8c54cff433f0c5d653320637f089e`. Per-request deadlines and worker timeout/termination/recovery remain untested. G9.42 was not run against this commit.

**Updated bounded conclusion:** all four public task routes have initial synthetic task-level acceptance coverage in each of the five backend environments. This is test evidence, not 20 final suitability verdicts. All G1–G8 evidence records, representative workloads, selector policy and remaining operational gates are still required. `production_approval=false` remains invariant.


## 9. SNAP request-deadline implementation follow-up — 2026-11-24

**Exact source:** `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86`  
**Workflow:** [AE-32C Native Graph Backend Conformance run 45385374806](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45385374806)

The adapter implementation now bounds each worker request's stdin write/flush and stdout response read. The default deadline is 120 seconds, configurable through `AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS`, with an upper bound of 600 seconds. Graceful close has a five-second maximum.

The Docker launch records the worker's exact container ID using `--cidfile`. A timed-out request triggers a bounded attempt to `docker rm --force` the recorded container, followed by bounded termination/kill of the host Docker client, protocol-stream closure and temporary-directory cleanup. A timed-out adapter is not automatically restarted; a new adapter instance is required.

The latest exact-source run reports:
- SNAP adapter protocol/restriction test step: **success**;
- SNAP M7.4 task-level acceptance step: **success**;
- SNAP synthetic E.8.5 conformance: **success**;
- NetworkX, SciPy, python-igraph and graph-tool jobs: **success**;
- SNAP repository-backed E.8.8: **in progress** at the last inspection, approximately 35 minutes after the step began.

The adapter test module exercises blocked write, blocked read, blocked close, invalid timeout values and the recorded `docker rm --force` command. Its process and Docker command are simulated/mocked. It does not prove cleanup against a real unresponsive container. No final E.8.8 SNAP artifact or conclusion was available, so the run is not accepted as a complete five-backend E.8.5/E.8.8 matrix.

G9.42 includes the adapter test file and M7.4 suite, but has not been dispatched against this latest exact revision. Formal task/backend suitability verdicts remain pending; preserve `production_approval=false`.

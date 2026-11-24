# AE-32C M7.4 — Initial Task Assessment Validation Record

**Status:** Initial STRUCTURAL / DEPENDENCY / PATH task-level acceptance suite passed across all five backend environments; formal suitability verdicts remain pending.  
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

This run does not establish any final suitability verdict for the 15 task/backend pairs.

1. **Workload representativeness:** the M7.4 fixture is a focused five-node synthetic graph. It is not a representative or scale-complete test of the five M7.2 workload families, real repository evidence density, production graph sizes, memory pressure or throughput.
2. **PATH domain interpretation:** generic graph path/evidence traversal is tested. Claim-to-evidence reconstruction, locator correctness and source-content follow-through remain distinct requirements.
3. **IMPACT:** not tested. Multi-source budget allocation, deterministic candidate merging, per-source attribution, ownership/evidence resolution, cycle scanning and incomplete-result reporting remain unqualified.
4. **SNAP lifecycle:** image identity is recorded for this run, but request deadlines, timeout propagation, forced termination and worker recovery remain open.
5. **Selector policy:** this change does not alter the generic first-match selection behavior or require task-specific acceptance states at selection time.
6. **G9.42:** the new test file was added to the G9.42 profile, but G9.42 was not dispatched against this commit. The passing evidence here comes from run 45381213888.
7. **Promotion:** no library is declared universally or comparatively superior; no runtime selection policy is activated.

## 7. Bounded conclusion and next gates

**Supported statement:** At source SHA `942b54f8948286b4727ca208fdfa553e019437b9`, the existing public STRUCTURAL, DEPENDENCY and PATH service routes passed the initial synthetic semantic-acceptance test suite in each of the five configured backend environments. Each tested route reported its expected native query mode and positive local-adjacency telemetry, matched the reference service on asserted semantic output, and left the canonical graph unchanged.

**Not supported:** a final suitable/conditionally suitable/not suitable decision, workload-wide task suitability, claim-to-evidence correctness, full IMPACT suitability, bounded SNAP request operation, selector authorization, production approval.

Next gates are to expand task-specific workload and evidence records, assess IMPACT independently, add SNAP request deadline/cleanup/recovery verification, resolve selector policy separately, and run G9.42 against an exact Stage1 commit when dispatch capability is available.

`production_approval=false` remains invariant.

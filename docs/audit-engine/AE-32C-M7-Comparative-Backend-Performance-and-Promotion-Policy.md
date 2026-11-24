# AE-32C M7 — Task Suitability and Operational Characterization

**Status:** M7.0 protocol complete; M7.1 closed; M7.2 bounded traversal campaign accepted; M7.3 detached dossier accepted for its stated verification scope (G9.42 run `44943859099`, manual run `44945256220`); M7.4 expanded STRUCTURAL / DEPENDENCY / PATH / IMPACT seeded-topology acceptance passed across all five backends in run `45395352748`; the complete E.8.5/E.8.8 matrix and aggregate summary passed. Formal task/backend suitability verdicts remain pending.  
**M7.1 workflow revision:** `main` SHA `182d0009f1c759c46813e3a1cbbf34d22c247acb`  
**M7.1 benchmark source:** Stage1 SHA `342c9d55b1dc49ccf93759d0dce203723485ef17`  
**M7.2 implementation:** `tools/gb06_task_suitability_campaign.py`  
**M7.2 tests:** `tests/semantic_graph/test_m72_task_suitability_campaign.py`  
**M7.2 campaign source SHA:** `1122916e8a56abec43cf3d42f8b2d252533e81c1`  
**M7.3 verifier source snapshot:** `3aee9dcadd46348a80bb5a7433276e8ce655a122`  
**Manual campaign controller:** [m7_2_manual_task_suitability_campaign.yml](https://github.com/snoopdock/Finite_element_analysis_project/blob/main/.github/workflows/m7_2_manual_task_suitability_campaign.yml), committed to `main` at `64fa7e662ffa5359fe4430b9273aa4a1bf6691f5`  
**Target branch:** `stage1/section-uuids` only.  
**Authority boundary:** `production_approval=false`; no automatic backend selection, scientific approval, graph mutation, or task-suitability decision is granted by M7.

---

## 1. Corrected objective

The five graph libraries are **computational options**, not contestants in a universal performance competition. The audit engine may need different computational capabilities for different problem classes. Backend suitability is therefore conditional on the operation, graph shape, semantic-preservation requirements, runtime environment, deployment constraints and evidence obligations.

The governing question is:

> Given a defined audit-engine task and its input characteristics, which computational option satisfies the task's correctness and representation requirements, provides the required native operation, and has acceptable integration and operational costs?

M7 must not produce a universal winner, rank libraries on a single scalar, or infer that one backend should replace another. A backend may be suitable for one task and unsuitable for another. Multiple backends may remain useful simultaneously.

**Timing is diagnostic evidence, not the decision objective.** It helps characterize the operational cost of a backend when it is already a candidate for a particular task. It is not an eligibility criterion by itself and is not converted into a universal score.

## 2. Architectural boundary

The canonical `SemanticGraph` remains authoritative for semantic identities, directed typed edge occurrences, attributes, metadata, evidence and provenance. A native library is a replaceable computation projection. It does not become the semantic source of truth.

The M7 experiments preserve the accepted M1–M6 constraints:

- canonical graph identity and edge-occurrence identity are stable across projections;
- parallel edges, self-loops, direction and relation types are not silently discarded;
- the exact native query path is observed and reported;
- reference traversal and parity checks gate the admission of measured observations;
- query bounds, ordering, result semantics and evidence reconstruction remain controlled by the audit-engine layer;
- unavailable or unsupported native capabilities are reported as such, not silently emulated and mislabeled;
- benchmark output cannot mutate graph state, choose a backend, approve scientific claims or set production approval.

This is consistent with ADR-032: graph libraries define how computation is performed; the semantic graph defines what the entities and relationships mean.

## 3. Candidate task classes and library roles

The following are **candidate roles to investigate**, not completed suitability decisions:

| Candidate audit-engine task | Relevant computational properties | Potentially relevant options | M7 evidence still required |
|---|---|---|---|
| Dependency/context traversal | Directed local adjacency, bounded traversal, deterministic ordering, exact edge occurrences | NetworkX, igraph, graph-tool, SNAP; SciPy where sparse adjacency is useful | Task-specific parity, native-path proof, metadata/evidence reconstruction and operational constraints |
| Change-impact candidate discovery | Reachability, degree skew, hub handling, bounded expansion, disconnected regions | NetworkX, SciPy, igraph, graph-tool, SNAP | Representative impact workloads and exact impact-result parity |
| Claim/evidence relationship exploration | Parallel typed edges, self-loops, relation filters, rich metadata and provenance | NetworkX, igraph, graph-tool, SNAP; SciPy only with explicit side-channel treatment | Occurrence-level identity and evidence reconstruction, not just endpoint connectivity |
| Sparse numerical graph operations | Sparse matrix/vector operations, CSR/CSC access, numerical semantics | SciPy is an obvious candidate to evaluate | Numerical operation contract, matrix/side-channel mapping, numerical tolerance and independent numerical oracle |
| Global graph analysis | Components, centrality, community or other graph-wide algorithms | Evaluate igraph, graph-tool, NetworkX, SNAP and SciPy according to the exact algorithm | Algorithm-specific result semantics, scaling/resource envelope and audit use case |
| Isolated or constrained execution | Process boundary, dependency isolation, serialization, worker lifecycle and reproducibility | SNAP worker; other backends if isolation becomes a requirement | End-to-end costs, failure recovery, worker security and provenance |

The role descriptions above are not endorsements. Package capabilities, existing adapters and native conformance are necessary evidence, but they do not establish that a library is the correct choice for a future audit task.

## 4. M7.1 — Five-backend native smoke gate (closed)

Run [44937517812](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44937517812) was triggered by `workflow_dispatch` and completed all eight jobs successfully.

- Workflow revision: `182d0009f1c759c46813e3a1cbbf34d22c247acb`.
- Requested source: `stage1/section-uuids`.
- Immutable benchmark source: `342c9d55b1dc49ccf93759d0dce203723485ef17`.
- Requested configuration: 15 measured repetitions and 5 warm-up calls per query.
- All five backends produced seven-query reports; all five independent report verifications returned `status=verified`.
- The report configuration assertions passed for all five backends.
- All five reports preserved matching query result digests and the expected native query mode.

This closes the M7.1 smoke and input-propagation gate. The five jobs ran on separate hosted runner instances. Their timings are not a controlled cross-backend comparison and must not be ranked. The run establishes native-path execution and report integrity for the fixed E.8.5 fixture, not broad task suitability.

## 5. M7.2 — Controlled workload families and bounded multi-seed campaign

### 5.1 Scope of the first campaign

M7.2 introduces deterministic workload families that vary graph characteristics relevant to audit-engine traversal:

| Workload ID | Shape represented | Audit-engine motivation |
|---|---|---|
| `sparse_dependency` | Sparse directed dependency graph with a chain backbone and seeded additional edges | Dependency/context retrieval |
| `hub_impact` | Degree-skewed graph with a high-out-degree hub | Change-impact candidate discovery |
| `parallel_evidence` | Repeated endpoint pairs, multiple relation types, self-loops and evidence metadata | Claim/evidence relationship exploration |
| `disconnected_components` | Multiple disconnected small components | Isolated audit subgraphs and bounded context |
| `dense_local_neighborhood` | Relatively dense local directed neighborhoods | High-local-degree traversal |

Each generated workload is bound to a generator version, seed, node and edge-occurrence counts, workload parameters, graph SHA-256 and canonical graph fingerprint. The generator uses deterministic Python PRNG seeds and retains canonical semantic edge occurrences.

The shared query corpus exercises outgoing, incoming and bidirectional neighborhoods, relation filtering and bounded impact traversal. Every query is checked against the independent canonical `GraphTraversalEngine` reference. The native query mode and adjacency lookup telemetry are required before a report is accepted.

### 5.2 Campaign structure

The campaign is intentionally **per backend**. Each backend report contains all selected workload families and all selected seeds for that backend. This allows the same workload definitions and semantic expectations to be replayed for every available computational option without turning their measurements into a contest.

Default bounded configuration:

- five workload families;
- two distinct ascending deterministic seeds by default (2–5 permitted);
- three timed repetitions per query by default (3–15 permitted);
- one warm-up call per query by default (0–5 permitted);
- one report per backend and execution environment.

The runner records construction time, raw per-query observations, descriptive median/p95/minimum/maximum/MAD, native adjacency counters, backend/library version, Python/platform provenance and worker metadata where supplied. Reports retain each seed/workload case separately; observations are not flattened into a fictional independent sample.

The M7.2 implementation does not claim process-level memory attribution. The initial campaign records the available runtime and worker metadata but does not treat a process high-water mark or backend-specific storage bytes as comparable memory measurements. A properly isolated memory study remains a later task.

### 5.3 CLI

Run one backend in an environment where that backend's declared dependencies and, for SNAP, its isolated worker are configured. The manual five-option controller is [m7_2_manual_task_suitability_campaign.yml on main](https://github.com/snoopdock/Finite_element_analysis_project/blob/main/.github/workflows/m7_2_manual_task_suitability_campaign.yml). It resolves the Stage1 source ref once and runs each backend in its own dependency environment:

```bash
python tools/gb06_task_suitability_campaign.py run \
  --backend networkx \
  --seeds 20261101,20261102 \
  --repeats 3 --warmup 1 \
  --report reports/m7-2-networkx.json

python tools/gb06_task_suitability_campaign.py verify \
  --report reports/m7-2-networkx.json
```

Replace `networkx` with one of `scipy`, `igraph`, `graph-tool` or `snap` for the corresponding backend environment. Workload families can be restricted with `--workloads` using a comma-separated subset of the declared workload IDs. The workflow's default configuration runs the complete five-family, two-seed campaign for each backend. The jobs are intentionally separate; the workflow does not compare or rank their timings.

### 5.4 Independent verification

The verifier reconstructs each deterministic graph from the declared workload ID and seed, recomputes its canonical graph digest and fingerprint, regenerates the query corpus, and replays expected results through the reference traversal. It recomputes all timing aggregates, checks sample counts and verifies the exact native query-mode label and authority boundary.

A report digest detects post-generation changes but does not cryptographically authenticate the timing observations or the machine that produced them. The verifier can establish internal consistency and reproducibility of the workload/result claims; it cannot independently rerun historical wall-clock samples.

### 5.5 Explicit exclusions

This first M7.2 campaign measures bounded semantic traversal across representative graph shapes. It does **not** yet execute or qualify:

- sparse numerical linear algebra;
- centrality or other global graph algorithms;
- community detection;
- ontology reasoning;
- end-to-end repository evidence reconstruction;
- full audit-engine task latency;
- isolated memory measurements or independent hardware-population trials.

Those are distinct tasks and require their own operation contracts, oracle results, workload generators and suitability criteria. They must not be inferred from a traversal campaign.

## 6. M7.3 — Independent campaign dossier verification

M7.3 will extend verification across detached artifacts and multiple backend reports. It should validate workload/seed coverage, report provenance, backend implementation revision, environment strata, exact native-path evidence, parity and aggregate mathematics. It must reject mixed source revisions and malformed or injected selection/approval fields.

M7.3 must not manufacture a combined ranking from independent runner jobs. If two backends are ever measured in the same controlled environment, any timing comparison must still be reported only as a task-specific operational observation with its workload and environment boundaries.

## 7. M7.4 — Task-specific suitability dossier

M7.4 will map audit-engine tasks to required capabilities and evidence. A suitability statement must identify:

1. the exact audit operation and why the operation exists;
2. graph size, topology, directionality, multiplicity and metadata requirements;
3. correctness, occurrence identity and evidence/provenance invariants;
4. required native algorithm/API and whether it is actually implemented;
5. dependency, deployment, worker-isolation and failure-recovery constraints;
6. workload-specific resource and latency observations, including limitations;
7. unsupported cases and fallback behavior;
8. the implementation and validation snapshot to which the statement applies.

The outcome may be “suitable for this task,” “conditionally suitable,” “not suitable,” or “insufficient evidence.” It is not a global library ranking. Any runtime selector policy remains a separate, explicit architectural decision and cannot be inferred from M7 timing data.

## 8. Acceptance and authority

M7.2 is accepted only when:

- the deterministic workload generator and bounds are tested;
- all workload families reconstruct exactly from their manifests;
- the common query corpus passes independent reference parity;
- each backend report proves its expected native query mode and records native adjacency telemetry;
- every requested seed/workload/query sample is present;
- the independent verifier rejects rehashed workload, result, aggregate and authority forgeries;
- exact-source G9.42 validation passes;
- all five backend campaign reports are produced and verified against the same Stage1 source revision, with environment differences disclosed;
- no winner, automatic backend selection, task-suitability decision or production approval is asserted.

`production_approval=false` remains invariant. M7 evidence does not establish scientific truth, diagnostic quality or permission to mutate the canonical graph.

## 9. Milestone sequence

- **M7.0 — Baseline freeze and protocol:** complete.
- **M7.1 — Five-backend smoke harness and input propagation:** closed by run `44937517812`.
- **M7.2 — Task-suitability workload families and bounded multi-seed campaign:** accepted for the declared bounded semantic-traversal workload scope; five-backend reports verified in run `44940960831`.
- **M7.3 — Detached report verification and descriptive evidence dossier:** closed for artifact/report/log provenance and consistency verification in run `44945256220`; no historical timing re-execution or physical-runner attestation is claimed.
- **M7.4 — Task-specific suitability assessment and explicit policy:** contract frozen; initial STRUCTURAL / DEPENDENCY / PATH tests passed in run `45381213888`; all four task routes now have initial synthetic acceptance coverage across the five backends in run `45382782600`; complete task/backend evidence records and formal verdicts remain pending.

## 10. Architectural references

- ADR-013 — Semantic Graph Backend Selection Policy.
- ADR-032 — Semantic Graph Computation Backend Boundary.
- `audit_engine/semantic_audit/graph/backend/adapter_interface.py`.
- `audit_engine/semantic_audit/graph/backend/capability_registry.py`.
- `tools/gb05_native_backend_performance_benchmark.py` — M7.1 smoke harness.
- `tools/gb06_task_suitability_campaign.py` — M7.2 seeded workload campaign.
- `tests/semantic_graph/test_m7_native_backend_performance_benchmark.py`.
- `tests/semantic_graph/test_m72_task_suitability_campaign.py`.
- `tests/semantic_graph/test_m74_task_suitability_acceptance.py` — first public-service task-level acceptance tranche.
- `tools/gb07_campaign_dossier.py` — M7.3 detached campaign verifier and dossier generator.
- `tests/semantic_graph/test_m73_campaign_dossier.py` — M7.3 adversarial dossier tests.
- `.github/workflows/m7_3_detached_campaign_dossier.yml` — manual M7.3 detached-artifact verification controller on main.
- `validation/profiles/G9.42.yaml` — deterministic validation profile.

Historical G6.1/G6.2 artifacts remain valid for their original NetworkX/SciPy exported-representation workloads. They are not substituted for M7 native-path or task-suitability evidence.


## 15.5 M7.2 exact-source execution and acceptance — 2026-11-21

The M7.2 five-option campaign completed in [run 44940960831](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44940960831). All eight workflow jobs passed: actionlint, immutable source resolution, five backend campaign/report jobs and the final summary gate.

- Workflow controller revision on main: cafa0d1be5c09eb092c1bc2467b540f20acb22b9.
- Immutable Stage1 campaign source: 1122916e8a56abec43cf3d42f8b2d252533e81c1.
- Exact-source G9.42 validation: [run 44940231437](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44940231437), successful against the same Stage1 SHA.
- All five reports used seeds 20261101, 20261102, five workload families, 15 measured repetitions and 5 warm-up calls per query. The 15/5 values were intentionally selected and are within the declared bounds.
- Each backend report contains 10 workload/seed cases, 50 query records, 750 timed observations and 250 warm-up calls.
- Across all five reports: 3,750 timed observations and 1,250 warm-up calls.
- All five reports share the same source revision, run ID and attempt. Graph digests/fingerprints and corresponding query result digests match across backends. Each report records five preflight parity queries per case, zero parity failures, its expected native query mode and nonzero native adjacency telemetry.
- The reports retain backend-specific library versions and runner provenance. NetworkX, SciPy, igraph and graph-tool ran on Azure-hosted Linux runners; SNAP ran on an AWS-hosted Linux runner with its isolated CPython 3.9 worker. These are separate execution environments. No cross-runner timing ranking or winner is inferred.

The five GitHub artifact identities and report digests are retained in the campaign evidence:
- NetworkX artifact 14721960675; report SHA-256 7226f66f86543de652d53df1479b67b2b1e51769eba08ff4658f78147a39700a.
- SciPy artifact 14722110390; report SHA-256 802d874c5d2941d67cbdf061e5a9a7e4298bc8ee2b56f87de7073469173b26da.
- igraph artifact 14721840765; report SHA-256 41ef8303906197169a440822143f67bee7bbfe9940275e3d24d94bf7b03feb4b.
- graph-tool artifact 14721268701; report SHA-256 92b83c4028bb2d64a1915e748c091ced4cf944cdc96e6723b4380185e265767a.
- SNAP artifact 14721029139; report SHA-256 43f6d57416a213d8f79f6f5c19d19adc5d5c0668aa1c54ba2393ecc2867b6565.

**Decision:** M7.2 is accepted for its defined bounded semantic traversal scope. This does not qualify numerical linear algebra, solvers, centrality, community detection, ontology reasoning, full repository evidence reconstruction or end-to-end audit-engine latency. It does not establish a backend winner, automatic selector, scientific approval or production approval.

## 15.6 M7.3 independent detached-artifact dossier — implementation

M7.3 adds tools/gb07_campaign_dossier.py, tests/semantic_graph/test_m73_campaign_dossier.py, and the G9.42 profile entry for the new test module. The manual controller is .github/workflows/m7_3_detached_campaign_dossier.yml on main, updated on main through bd5260926d468876dc58182e2c310237ffe9e5c9.

The verifier consumes detached reports, run/verification logs and a GitHub Actions artifact metadata manifest. It checks:
- exactly one unexpired artifact for each of the five backends, with artifact IDs, GitHub SHA-256 metadata, campaign run/attempt naming and one controller revision;
- exact report schema, source revision, workflow name, run ID and attempt;
- each report through the M7.2 deterministic report verifier and agreement with its detached verification log;
- complete five-family workload and seed coverage, identical configuration and task scope;
- canonical graph digest/fingerprint equality and corresponding query-result digest equality across all backends;
- expected native query mode, preflight parity counts/failures, native adjacency telemetry and campaign-wide sample arithmetic;
- a descriptive environment-strata summary without pooling or ranking timings.

The dossier records the GitHub artifact digest metadata and SHA-256 values of extracted report/log files. The workflow obtains the artifact metadata from the GitHub Actions API and downloads each exact backend artifact for the selected run attempt. The verifier validates the metadata's presence and format and records it; it does not independently re-hash the ZIP archive bytes. The report's internal digest is an integrity check, not a signature. The verifier does not claim to re-execute historical timing samples or independently authenticate the physical runner.

The tests include missing/expired artifacts, mixed source revisions, configuration mismatch, authority escalation, injected selection fields and detached-log mismatch. The G9.42 profile now includes this test module.

**M7.3 status:** closed for the bounded detached-artifact verification scope. Exact-source G9.42 run `44943859099` and manual detached-dossier run `44945256220` passed; the generated Markdown/JSON dossier was inspected. The verifier checks report/log/artifact identity and consistency, not historical re-execution or physical-runner attestation. Keep `production_approval=false`.


## 11. M7.4 assessment contract

The task-specific assessment contract is maintained in [AE-32C M7.4 Task-Specific Backend Suitability Assessment Contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md). It treats STRUCTURAL, DEPENDENCY, PATH and IMPACT as distinct operations and requires each backend/task pair to be assessed against the actual public analyzer/service path, semantic/evidence invariants, workload envelope and operational environment. The four possible outcomes are suitable, conditionally suitable, not suitable and insufficient evidence. The contract explicitly forbids extrapolating higher-level task suitability from the M7.2 traversal campaign alone.

The contract is not a runtime selector and grants no promotion authority. The libraries remain computational options serving different problem classes. A future selector requires a separate architectural decision. `production_approval=false` remains invariant.


## 16. M7.4 initial task-level evidence — 2026-11-24

M7.4 is now in its executable assessment phase. The contract in [AE-32C M7.4 Task-Specific Backend Suitability Assessment Contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md) remains the controlling decision framework.

The first implementation commit, Stage1 SHA `942b54f8948286b4727ca208fdfa553e019437b9`, adds `tests/semantic_graph/test_m74_task_suitability_acceptance.py`, includes it in G9.42, and runs the selected-backend test partition in each of the five existing backend environments. The push-triggered run [45381213888](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45381213888) completed successfully. NetworkX, SciPy, python-igraph, graph-tool and SNAP each reported 7 passed / 28 intentionally skipped; the skips are the four non-selected backend partitions. All five E.8.5/E.8.8 jobs and the aggregate summary succeeded.

The suite exercises STRUCTURAL, DEPENDENCY and PATH through `SemanticGraphAnalysisService`, with independent expected-result assertions, reference-service comparison, native query telemetry, per-query parity, evidence/edge-occurrence checks, bounds and canonical-graph immutability. The small synthetic fixture is diagnostic, not representative workload or scale coverage. The evidence supports initial semantic/native-path statements for the tested public routes only; it does not issue final suitability outcomes for any backend/task pair.

The SNAP workflow recorded Docker image ID `sha256:f94d166165f7676f031bb476a79b0c7e112ef65f0f9c4ef5027844891f1eb4b3` for this execution. This addresses image identity for that run, not the unresolved lack of a per-request worker response deadline or the need for termination/recovery tests.

G9.42 includes the new test module but was not run against this commit. IMPACT, claim-to-evidence source follow-through, representative workload envelopes, selector acceptance-state enforcement, and SNAP timeout/recovery remain open. The full source-bound evidence and test logs are recorded in [AE-32C M7.4 Initial Task Assessment Validation](AE-32C-M7.4-Initial-Task-Assessment-Validation.md).

**Current M7.4 position:** initial STRUCTURAL / DEPENDENCY / PATH task tests are green across the five environments; the milestone is not complete and no task/backend suitability verdict, ranking, selector activation or production approval is made. Keep `production_approval=false`.


## 17. M7.4 IMPACT follow-up — 2026-11-24

The M7.4 acceptance suite now covers the IMPACT route as well as STRUCTURAL, DEPENDENCY and PATH. Exact corrected test commit `ff6fe8226d6417b0832a17b8bed397217f72a303` was exercised in [workflow run 45382782600](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45382782600). NetworkX, SciPy, python-igraph, graph-tool and SNAP each reported 11 passed / 44 intentionally skipped for the backend-selected suite; all five E.8.5/E.8.8 jobs and the aggregate summary passed.

The IMPACT tests cover multi-source attribution and deterministic candidate merging, per-source paths, one-hop ownership evidence, cycle records and their edge evidence, global change-set budget exhaustion, cycle-scan edge-limit behavior and invalid change-set cardinality. Native traversal and reference parity are asserted for ownership and reverse-dependency query calls. The cycle scan remains a canonical `SemanticGraph.edges` operation, not a native backend SCC operation. This hybrid execution boundary must be retained in later records.

The first IMPACT test attempt at `b6b81b60753cf36334281f19c3ff64aea5abe7b9` failed because the test expected a second-hop `MEMBER_OF` edge in the one-hop file ownership evidence. The test oracle was corrected at `ff6fe8226d6417b0832a17b8bed397217f72a303`; no analyzer/runtime behavior was changed for that failure. The corrected run passed.

The SNAP image identity for this run is `sha256:8aa923b1de4d7b2ca7301cb27556178e35e8c54cff433f0c5d653320637f089e`; per-request deadlines and worker timeout/recovery remain open. G9.42 was not dispatched against this commit. The M7.4 matrix now has initial test coverage for the 20 task/backend combinations, not final suitability verdicts. Representative workload, environment and operational dossiers remain pending. Keep `production_approval=false`.


## 18. SNAP request deadline and cleanup implementation follow-up — 2026-11-24

Stage1 commit `2755043ba5f985225c8794c93d72b76567ff8b83` introduced bounded worker RPCs; `fe6b5474be56f769309f66a4e56f82a44c1890bf` added container-ID capture and forced removal; `f03d2768b3863f74719079e7cde458b02f2b87b4` corrected the Docker cleanup test fixture; and `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86` corrected constructor initialization order.

The adapter uses a 120-second default request deadline (maximum 600 seconds) across stdin write/flush and stdout read, and a five-second close deadline. On timeout it attempts a two-second-bounded `docker rm --force` against the captured container ID, then terminates/kills the Docker client and closes streams. An adapter that times out is not restarted in place.

Exact-source [run 45385374806](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45385374806) checked out `6b32b0bad6390d5f18d8fa6ce7cb99a321c06a86`. The SNAP adapter test, M7.4 task suite and E.8.5 synthetic step all succeeded. NetworkX, SciPy, python-igraph and graph-tool jobs succeeded. At the last inspection, SNAP E.8.8 remained in progress after approximately 35 minutes, with no final SNAP repository report or artifact. This is not a completed E.8.5/E.8.8 matrix result.

The timeout cleanup tests use a mocked process and Docker command. Live forced removal of a deliberately stalled Docker worker remains unproven. The next M7.4 SNAP gate is to close the current E.8.8 result, then add or execute a real Docker lifecycle test for intentional worker non-response. The G9.42 profile contains the relevant adapter and M7.4 tests, but the profile has not been dispatched against this source revision. Keep all suitability decisions pending and `production_approval=false`.

## 19. Live SNAP container-removal test — 2026-11-24

At exact Stage1 source `7a77b52c316c60ffb8f433af2bbd1b742f389972`, the E.8.5/E.8.8 workflow runs `tests/semantic_graph/test_snap_worker_docker_lifecycle.py`. The live Docker lifecycle test `tests/semantic_graph/test_snap_worker_docker_lifecycle.py` passed. It built a disposable worker container that deliberately did not respond, observed the adapter request deadline, verified `docker rm --force` used the exact container ID captured by `--cidfile`, and confirmed that `docker inspect` could no longer find the container. This is direct live Docker evidence on the tested GitHub-hosted runner, not merely a mocked process test.

In exact-source workflow run `45391619634` at `7a77b52c316c60ffb8f433af2bbd1b742f389972`, the SNAP adapter protocol/restriction tests, live Docker timeout cleanup test, M7.4 task suite and synthetic E.8.5 all succeeded. NetworkX, SciPy, python-igraph and graph-tool jobs also succeeded. At the last inspection, SNAP repository-backed E.8.8 remained `in_progress` after approximately 12 minutes; no final SNAP repository report or artifact was available. Do not count the matrix as complete.

The G9.42 profile includes the SNAP adapter, live Docker lifecycle and M7.4 task tests, but exact-source G9.42 has not been dispatched. The main-branch dispatcher requires `workflow_dispatch`; that dispatch operation is not exposed by the connected GitHub actions tools.

Do not treat the still-running E.8.8 step as acceptance. Keep task/backend verdicts pending and `production_approval=false`.


## 20. Expanded M7.4 seeded workloads and complete SNAP E.8.8 close-out — 2026-11-24

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

SNAP adapter protocol, real Docker timeout cleanup, RepositoryEvidenceTools backend resource teardown, M7.4 task acceptance, E.8.5 and E.8.8 all passed. The first expanded E.8.8 execution at run `45391619634` emitted a passed report but failed to exit because the repository runner did not explicitly close the backend adapter. The E.8.8 runner now closes `RepositoryEvidenceTools` in `finally`; the latest logs explicitly reached `backend_resources_closed` before report output.

The SNAP E.8.8 report completed with `status: passed` and source SHA `51d025fd328b00a59988a05fe72d9092262434f5`. It records 43 attempted/successful backend queries, 43 reference-parity verifications, zero query failures and zero parity failures; 45 native adjacency lookups and 86 native edge occurrences read. The repository fixture is complete: 26 nodes, 41 edge occurrences, 9 indexed files, graph fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`, and source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. The runner followed graph-surfaced paths to two source reads (`main.py` and `tests/checks.py`) and verified both SHA-256 values.

The per-operation context telemetry is also complete: trace context 7/7 parity-verified adjacency queries; workflow context 16/16; nested workflow context 16/16. The SNAP worker was CPython 3.9.25 / SNAP 6.0.0, image ID `sha256:a3ab78cf8512048adfc3570bff591772c1542dfb09226363142c6779934f59a5`, with the declared isolated container restrictions. E.8.8 used a 30-second worker request deadline.

The initial expanded test run failed only because the IMPACT fixture requested depth 6 where the analyzer allows 1–5. That test input was corrected to 5; no runtime analyzer algorithm was changed. The corrected exact-source run passed.

These results are semantic task-fit tests, not cross-backend performance comparisons. Formal G1–G8 records and task/backend verdicts remain pending. Exact-source G9.42 has not been dispatched; keep `production_approval=false`.

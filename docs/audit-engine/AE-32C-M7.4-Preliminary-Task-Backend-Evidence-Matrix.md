# AE-32C M7.4 — Preliminary Task/Backend Evidence Matrix

**Record type:** Preliminary evidence ledger; not a suitability approval  
**Branch:** stage1/section-uuids  
**Latest task-test source:** 0b37e79c9942e483cea770fc96138c4f185753e1 (earlier evidence snapshots remain individually source-bound)  
**Latest E.8.5/E.8.8 regression:** [45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671), attempt 1, success; G7 detached pass for this exact set is [run 45602963647](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647)  
**Latest aggregate summary job:** 139165860984, success  
**Controlling contract:** [M7.4 Task-Specific Backend Suitability Assessment Contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md)  
**Validation evidence:** [M7.4 Initial Task Assessment Validation](AE-32C-M7.4-Initial-Task-Assessment-Validation.md)  
**Authority:** production_approval=false; no global ranking, winner, automatic selection or runtime promotion.

---

## 1. Decision status

The expanded M7.4 acceptance module passed in all five backend environments. Each selected-backend job reported 21 passed and 84 intentionally skipped cases. This provides positive task-scoped semantic and native-path evidence for all 20 task/backend combinations (four public tasks × five backends).

**This is not yet 20 suitability approvals.** Under the M7.4 contract, an untested or only partially evidenced mandatory gate prevents a Suitable decision. The preliminary outcome for every pair below is therefore **Insufficient evidence**. The reason is not an observed parity failure; it is the remaining incompleteness in semantic boundary coverage, mutation/corruption safety, representative workload, operational envelope and task-domain qualification. The five-backend E.8.5/E.8.8 artifact integrity check (G7) was subsequently completed; see Section 9.

The five backends are task-relevant computational options, not competing products. This record does not rank them.

## 2. Source and test evidence

The latest E.8.5/E.8.8 source SHA is ed33bf68c49fd41506d5d7917fbdc77bf8e544e7. The task acceptance module was checked out at that exact source in all five backend jobs; earlier campaign results remain separately bound to their historical source SHAs.

| Backend | CI job ID | M7.4 result |
|---|---:|---:|
| NetworkX | 139164993004 | 21 passed; 84 expected skips |
| SciPy | 139164992886 | 21 passed; 84 expected skips |
| python-igraph | 139164992902 | 21 passed; 84 expected skips |
| graph-tool | 139164992523 | 21 passed; 84 expected skips |
| SNAP isolated worker | 139164993062 | 21 passed; 84 expected skips |

The 84 skips in each job are the four backend partitions not selected by that job. Across the matrix this is 105 passing backend-specific test executions and 420 expected skips; it is not 105 different test definitions.

The expanded tranche uses fixed seeds 20261101 and 20261102, the five seeded M7.2 topology generators, and three disjoint replicas of each base graph:

| Workload | Base graph | Three-replica assessment graph |
|---|---:|---:|
| sparse_dependency | 48 nodes / 96 edges | 144 nodes / 288 edge occurrences |
| hub_impact | 48 / 176 | 144 / 528 |
| parallel_evidence | 32 / 144 | 96 / 432 |
| disconnected_components | 64 / 128 | 192 / 384 |
| dense_local_neighborhood | 32 / 256 | 96 / 768 |

Each workload/seed/backend case exercises STRUCTURAL, DEPENDENCY, PATH and two-source IMPACT through the public service; compares semantic output with the reference service; checks native query mode, parity and adjacency telemetry; and verifies canonical graph immutability. These are synthetic task-fit workloads, not timing benchmarks or production repository captures.

## 3. Backend environment and native-path evidence

The library versions are read from the repository-backed E.8.8 reports; Python versions and SNAP worker details are bound to the same workflow's reports/logs.

| Backend | Library version | Python environment | Native query mode | Execution mechanism |
|---|---|---|---|---|
| NetworkX | 3.6.1 | 3.11.18 | networkx_successor_predecessor_adjacency | Directed MultiDiGraph successor/predecessor adjacency; keyed parallel occurrences |
| SciPy | 1.17.1 | 3.11.18 | scipy_csr_csc_adjacency | CSR outgoing / CSC incoming; semantic attributes and provenance retained in side channels |
| python-igraph | 1.0.0 | 3.11.18 | igraph_incident_edge_ids | Native incident edge IDs mapped to canonical occurrences |
| graph-tool | 3.9 | 3.11.18 | graph_tool_vertex_edge_iterators | Native per-vertex out_edges/in_edges iterators and edge-index mapping |
| SNAP | 6.0.0 | Orchestrator 3.11.18; isolated worker 3.9.25 | snap_isolated_worker_tneanet_edge_ids | TNEANet edge-ID access through versioned JSON-lines IPC in restricted Docker |

The SNAP E.8.8 worker image ID was sha256:a3ab78cf8512048adfc3570bff591772c1542dfb09226363142c6779934f59a5. Its tested policy was network disabled, read-only root, no writable mounts, all capabilities dropped, no repository mount, no provider credentials, 512 MiB memory, one CPU and 64 PIDs. E.8.8 used a 30-second request timeout; the adapter default is 120 seconds, maximum 600 seconds.

All five E.8.8 reports record 43 successful backend queries, 43 reference-parity verifications, zero query failures and zero parity failures, 45 native adjacency lookups and 86 native edge occurrences read over the common repository fixture. The fixture contains 26 nodes, 41 edge occurrences and 9 indexed files; graph fingerprint graph:1aca2caea6acabcf695a6118f7202b6e; source-manifest SHA-256 5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf.

## 4. G1–G8 gate assessment

| Gate | Evidence | Preliminary state | Remaining closure |
|---|---|---|---|
| G1 — Task definition | Four public query/analyzer paths and intended uses are specified in the controlling contract | Pass | Preserve the exact task and sub-operation boundaries in final records |
| G2 — Semantic correctness | Independent diagnostic fixtures, seeded workloads, reference parity, edge/evidence, direction, filters, bounds and incomplete states | Partial | Expand semantic boundary combinations and task-domain assertions beyond current synthetic cases |
| G3 — Public-path execution | Public service/analyzer calls, expected native modes, native telemetry, per-query parity, zero backend failures | Pass for tested traversal paths | Inspect all callers and unsupported branches; retain IMPACT hybrid boundary |
| G4 — Snapshot/mutation safety | Canonical graph immutability asserted through tested analyses | Partial | Stale/corrupt projection, mutation race and longer-running repeated-query cases remain open |
| G5 — Task workload | Five M7.2 seeded families, two seeds, three replicas; all four public tasks invoked | Partial | Representative audit corpus, scale envelope, degree/evidence density and pressure workloads remain untested |
| G6 — Environment/operations | Exact versions/Python, SNAP resource controls, deadlines, live Docker removal and explicit teardown tests | Partial | Startup costs, resource use under representative loads, cross-host portability and non-SNAP operational envelopes remain incomplete |
| G7 — Evidence integrity | Exact source SHA, run/attempt, source/graph manifest hashes, artifact IDs and archive digests recorded; G9.42 validation bundle independently verified in run `45400741779`; all five E.8.5/E.8.8 artifacts detached-verified in Section 9 | Pass, for the recorded evidence set | Preserve verifier, manifest, report hashes and archive digests; this is evidence-integrity closure, not runner attestation or task-suitability verdict |
| G8 — Scope discipline | Policy prohibits winner, global score, automatic selection and production approval | Pass | Preserve restrictions in future selector decisions |

## 5. Preliminary task/backend decision ledger

G1 is defined for each row. G2–G8 are assessed using the task-specific and backend-specific limitations in Sections 4 and 6.

| Task | Backend | G2 | G3 | G4 | G5 | G6 | G7 | G8 | Preliminary outcome |
|---|---|---|---|---|---|---|---|---|---|
| STRUCTURAL | NetworkX | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| STRUCTURAL | SciPy | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| STRUCTURAL | python-igraph | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| STRUCTURAL | graph-tool | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| STRUCTURAL | SNAP | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| DEPENDENCY | NetworkX | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| DEPENDENCY | SciPy | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| DEPENDENCY | python-igraph | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| DEPENDENCY | graph-tool | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| DEPENDENCY | SNAP | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| PATH | NetworkX | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| PATH | SciPy | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| PATH | python-igraph | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| PATH | graph-tool | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| PATH | SNAP | Partial | Pass, tested path | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| IMPACT | NetworkX | Partial | Partial, hybrid | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| IMPACT | SciPy | Partial | Partial, hybrid | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| IMPACT | python-igraph | Partial | Partial, hybrid | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| IMPACT | graph-tool | Partial | Partial, hybrid | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |
| IMPACT | SNAP | Partial | Partial, hybrid | Partial | Partial | Partial | Partial | Pass | **Insufficient evidence** |

This conservative outcome is intentional. Green task tests and repository conformance establish behavior at the tested source, fixture and environment; they do not close the entire suitability contract.

## 6. Task-specific and backend-specific boundaries

- **STRUCTURAL:** tested one-hop neighborhood, direction/relation filters, edge-occurrence/evidence retention and self-loop behavior. No global graph statistic or full structural-analysis workload is qualified.
- **DEPENDENCY:** tested bounded direct/transitive traversal, relation filters and incomplete/truncation states. This does not establish correctness of every repository dependency reconstruction or policy interpretation.
- **PATH:** tested generic bounded path and path-step evidence. Domain-specific claim-to-evidence reconstruction, locator correctness and source-content follow-through remain separate requirements.
- **IMPACT:** tested multi-source candidate merging/attribution, per-source paths, one-hop ownership resolution, risk/test/workflow/symbol candidates, budgets and cycle-scan bounds. Ownership and reverse-dependency traversals use the selected backend; dependency-cycle SCC detection still scans canonical SemanticGraph edges and is not a native backend SCC operation.

Additional representation constraints:
- SciPy CSR/CSC encodes topology; relation, metadata and evidence identity remain side-channel data.
- SNAP is isolated and has explicit request/cleanup behavior, but a timed-out worker is not automatically restarted.
- graph-tool runtime/distribution is environment-specific and tied to its recorded conda environment.
- no current test creates a cross-backend performance ranking; these are task-specific computation options.

## 7. Required next evidence

1. Expand G5 using task-specific audit-domain graph captures and boundary cases, including larger connected graphs, degree/evidence-density variation, multi-source sets near the 25-source limit, cycle scan limits and relation-vocabulary extremes.
2. Complete G4 stale/corrupt projection, mutation-race and repeated-query lifecycle checks for every adapter.
3. Complete G6 operational records: startup/teardown, resource use under declared workloads, portability and SNAP timeout/recovery behavior.
4. **Completed:** detached verification of the exact five-backend E.8.5/E.8.8 artifacts from run `45395352748`; see Section 9.
5. Complete PATH domain-specific evidence/locator/source follow-through.
6. Keep IMPACT canonical SCC behavior explicit. Native SCC support would require a separate API/algorithm contract and parity evidence.
7. **Completed:** exact-revision G9.42 was dispatched through the main-branch manual dispatcher with branch `stage1/section-uuids`, profile `G9.42` and regression mode `profile`; run `45400741779` passed against source SHA `d66f10b5c8af74b33a661c2453da3aca9982d565`. See Section 8 for run, test and evidence-bundle details.
8. Only after mandatory gates close should each pair receive one formal outcome from the contract vocabulary.


## 8. Exact-source G9.42 manual validation — 2026-11-24

**Workflow:** [Manual Validation Dispatcher run 45400741779](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45400741779), attempt 1, `workflow_dispatch`, conclusion `success`.

**Target source:** `stage1/section-uuids` at `d66f10b5c8af74b33a661c2453da3aca9982d565`. The workflow's `head_sha` / engine commit `ee4e4b769221d331b1d2726301349cd0c217ab03` identifies the `main` revision that supplied the dispatcher and central validation engine; it is not the source revision under test. The log records that the requested Stage1 branch was checked out and `git log -1` returned the target SHA above.

**Profile:** `G9.42`, regression mode `profile`; profile SHA-256 `5203344eb03bee4f2c9c3999ba697243f7d3f4224ec27e36ebccb9d09448a6a`. The Stage1 profile includes the M7.4 task-acceptance, SNAP worker adapter, live Docker lifecycle, E.8.8 cleanup and related graph/backend tests.

**Results:** 53/53 validation-engine unit tests passed; the targeted profile ran 846 tests (799 passed, 47 skipped, zero failures/errors); full regression ran 3,785 tests (3,730 passed, 55 skipped, zero failures/errors). In each invocation the M7.4 module reported 63 passes and 42 skips. Those 42 skips are the 21 graph-tool and 21 SNAP task-partition cases, intentionally unavailable in the generic Python 3.11.18 validation environment; the SNAP-specific adapter and live Docker lifecycle tests in this profile did execute and pass. The graph-tool and SNAP M7.4 task partitions were separately executed in their dedicated backend environments in run `45395352748`, where all five backends reported 21 passed / 84 other-backend skips.

**Evidence pipeline:** detached validation-report/digest verification passed; immutable evidence bundle publication passed; provenance catalog build and independent verification passed. Report SHA-256: `d12a924d7da5c29334c1df8e40072671e5771bc733e9c3c65e1395311ff831db`. Content-addressed bundle SHA-256: `decb5aa79605dad7bab4067d6700e8490aa3193c91b069098f87aa8a216a6266` (758,773 bytes). GitHub Actions artifact ID `14923188602`, archive digest `sha256:39a9be6f71e093d101c2eedc704a596ce816adb78d354c28ce8dac2dc0b5435d`.

**Interpretation:** the exact-source G9.42 dispatch gate is now closed for Stage1 SHA `d66f10b...`. This does not close the separate M7.4 G7 requirement to independently verify the five-backend E.8.5/E.8.8 artifact set from run `45395352748`; the G9.42 validation bundle is a different evidence object. G4 stale/corrupt projection and mutation-race coverage, representative G5 audit-domain workload evidence, broader G6 operational/resource envelopes, PATH claim-to-source follow-through and the explicitly hybrid IMPACT SCC boundary remain as described in the preliminary matrix. All 20 task/backend outcomes remain `Insufficient evidence`; no suitability, ranking, selection or production approval follows.

production_approval=false remains invariant.

## 9. G7 — Detached verification of the five-backend E.8.5/E.8.8 artifacts

**Status: Pass for this exact artifact set.** Run [45395352748](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45395352748), attempt 1, tested source `51d025fd328b00a59988a05fe72d9092262434f5` on `stage1/section-uuids`. Artifact IDs, sizes and GitHub Actions digests are recorded in `evidence/m74-e85-e88-run-45395352748/manifest.json`; the detached result is `evidence/m74-e85-e88-run-45395352748/verified-dossier.json`.

The verifier recomputed every ZIP digest and byte count, required exactly the expected E.8.5/E.8.8 report members, bound reports to backend/source/run/attempt and checked schema, native mode/version, case/query totals, parity, telemetry, projection round-trip, repository snapshot, source-read hashes, side-effect declarations and SNAP policy. All five artifact sets passed. Each backend records E.8.5 14/14 and E.8.8 43/43 parity-verified queries, with zero query/parity failures. The 11 adversarial verifier unit tests passed.

Verifier source SHA-256: `94f1b42f81fed87123aed8b77e1d0560609a9bfe895502c05afde2b00fa7179f`. G7 is closed for the exact downloaded evidence set. This is detached archive/report consistency verification, not historical workflow re-execution or physical-runner attestation. G2/G4/G5/G6 and task-domain qualifications remain open; all 20 task/backend outcomes remain **Insufficient evidence**. `production_approval=false` remains invariant.

## 10. G4 snapshot/mutation integrity test tranche — 2026-11-24

The five-backend G4 test module and E.8.5/E.8.8 workflow integration are recorded in [the G4 integrity dossier](AE-32C-M7.4-G4-Snapshot-and-Mutation-Integrity.md). The suite tests deep-copy snapshot isolation, stale canonical detection, mutation during native adjacency, corrupt/missing local occurrences, repeated-query stability, projection reconstruction and SNAP post-close behavior.

At the time this subsection was first recorded, the G4 test run was pending. Section 11 records the subsequent exact-source execution. **Gate status remains Partial, not Pass.** Residual limitations include repository-file non-mutation not being exercised by this in-memory suite, non-exhaustive concurrency schedules, and mutable native exports whose off-neighborhood corruption is not globally revalidated on every bounded query.

All 20 suitability outcomes remain Insufficient evidence. `production_approval=false`.

## 11. Exact-source execution of G4 synthetic integrity tests — 2026-11-24

Run [45413494767](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45413494767), attempt 1, executed `test_m74_snapshot_mutation_integrity.py` against Stage1 source `7447a6b6327b2f310012088767df8251577f6cb1`. Each of NetworkX, SciPy, igraph, graph-tool and SNAP reported 5 passed / 20 backend-selection skips; all five jobs and the aggregate summary succeeded.

**Gate status: Partial, not Pass.** The focused synthetic tests passed, but the contract also requires repository-file non-mutation and an acceptable treatment of mutable native exports/off-neighborhood corruption and broader mutation schedules. See [the G4 integrity dossier](AE-32C-M7.4-G4-Snapshot-and-Mutation-Integrity.md). All 20 task/backend outcomes remain Insufficient evidence; `production_approval=false`.

## 12. G4 off-neighborhood projection validation — implementation pending execution

The G4 implementation now revalidates the complete native projection before and after each bounded query. New tests target corruption of an edge outside the query neighborhood, mutation after local adjacency, and fresh SNAP worker audit RPCs. The five-backend workflow includes the expanded suite.

**Status: pending exact-source execution.** If the tests pass, they establish fail-closed detection for corruption present at preflight or persisting until postflight; they do not establish immutability or close mutation/restoration races. The two full scans add O(V+E) cost per traversal (and two worker audit RPCs for SNAP), which must be quantified under representative task workloads. Repository-file side-effect coverage remains open. G4 remains Partial; all 20 suitability outcomes remain Insufficient evidence.

## 13. Exact-source execution of off-neighborhood G4 integrity checks — 2026-11-24

[Run 45423628531](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45423628531), attempt 1, source `0790019b2d3ce4f4fe9c0f89d58c90eb3a689a9a`, passed the expanded G4 suite in all five backend environments: NetworkX 7, SciPy 7, igraph 7, graph-tool 7 and SNAP 8 passed. All backend jobs and the aggregate E.8.5/E.8.8 summary succeeded.

E.8.5/E.8.8 each recorded 14/14 and 43/43 parity-verified queries, zero parity failures. G4 remains Partial because repository-file side effects, broader concurrency/mutation-restoration races, the SNAP in-worker mutation boundary and G5/G6 cost characterization remain open. All 20 task/backend outcomes remain Insufficient evidence.


## 14. Corrected G4 cost characterization, Windows reparse-point coverage and latest E.8.5/E.8.8 regression — 2026-11-24

The earlier three-sample source-cost report is superseded because its per-file counter wrapper ran inside the timed load/validation phases and its p95 was only the maximum observation. Schema v3 moves read accounting to a separate unmeasured replay, verifies non-sensitive source counts/bytes against the reconstructed manifest, binds source/runner revisions, and reports ten single-process observations without a p95 claim.

Exact-source [G4 run 10](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007486), SHA `098a87394d972010f04466c540fcf5f43b490f9b`, passed 12 benchmark contract tests, both report-verification steps and the Windows compatibility job. Its Linux second-validation pass measured a 39.17 ms median for 1,857 files / 9,520,835 bytes; this is 0.839% of the observed pipeline median, not a no-validation counterfactual. The paired Windows Server 2022 / Python 3.11.9 job passed 27 tests with 46 skips, including explicit rejection of a directory-junction escape. See Sections 20 and 23 of the G4 dossier for the full method, ranges/MAD, platform caveats and remaining TOCTOU boundaries.

The latest five-backend E.8.5/E.8.8 regression [run 45473007901](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007901), source SHA `098a87394d972010f04466c540fcf5f43b490f9b`, completed successfully for NetworkX, SciPy, python-igraph, graph-tool and the isolated SNAP worker. Each backend recorded E.8.5 14/14 and E.8.8 43/43 parity-verified queries, with zero query/parity failures. The G4 snapshot/mutation suite reported 7 passed / 33 expected skips for the four in-process backends and 8 passed / 32 expected skips for SNAP. Repository side-effect/lifecycle tests reported 7 passed / 14 expected skips for the four in-process backends and 8 passed / 13 expected skips for SNAP. The M7.4 task-level acceptance suite reported 21 passed / 84 expected skips per backend. SNAP protocol, live timeout/cleanup, resource teardown, G4 and repository-backed E.8.8 steps all passed.

All five downloaded E.8.5/E.8.8 artifact ZIP hashes were independently recomputed and matched their Actions upload digests; their embedded reports identify the exact run source SHA and `passed` status. The artifacts from run `45473007901` were subsequently processed by the parameterized detached verifier in [run `45601021689`](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601021689), which passed G7 for that exact artifact set (Section 15). The later regression artifacts from run `45600944022` have not yet been through their own detached dossier; do not extend the G7 pass for run `45473007901` to this newer artifact set.

**Decision unchanged:** G4 remains Partial. G5/G6 and other incomplete M7.4 gates remain open. All 20 task/backend outcomes remain **Insufficient evidence**; `production_approval=false`. Computational backends remain task-specific options, not universal performance competitors.


## 15. Latest detached G7 verification and post-verifier regression — 2026-11-25

The E.8.5/E.8.8 artifact set from run `45473007901`, source SHA `098a87394d972010f04466c540fcf5f43b490f9b`, was independently detached-verified by [run 45601021689](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601021689). All five artifact archives matched exact IDs, byte counts and SHA-256 digests. The verifier checked the E.8.5/E.8.8 schemas, source/run/attempt identity, native modes and library versions, parity/query telemetry, projection round-trip, repository snapshot, context telemetry, source hashes, side-effect declarations, SciPy hybrid representation and SNAP image/policy/deadline. The detached dossier is [artifact 15015925967](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601021689/artifacts/15015925967). **G7 is Pass for run 45473007901 only.**

The verifier changes and provenance test were then exercised by the later five-backend E.8.5/E.8.8 regression [run 45600944022](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45600944022), source SHA `ed33bf68c49fd41506d5d7917fbdc77bf8e544e7`. All five backend jobs and the aggregate summary succeeded. Each backend reported 21/21 M7.4 task-acceptance passes, 14/14 E.8.5 parity-verified queries and 43/43 E.8.8 parity-verified queries, with zero query/parity failures. G4 snapshot/mutation tests passed 7 cases in each in-process backend and 8 in SNAP; repository side-effect/snapshot-race tests passed 7 cases in each in-process backend and 8 in SNAP. SNAP also passed protocol, live Docker timeout/cleanup and resource-teardown tests.

The G4 evidence is stronger but remains bounded. It includes in-root byte/mode read-only checks, source-snapshot consistency after external same-size edits, a tested active-read mutation schedule, ordinary change-and-restore detection between snapshot passes, and fail-closed behavior for a query waiting on a closed SNAP worker. It does not establish atomic repository-wide snapshot semantics, eliminate Windows reparse-point path-opening TOCTOU, cover all filesystem metadata/external side effects or close every mutation/restoration race. G4 remains Partial.

**Source separation:** run 45601021689 verifies the five-backend artifact set from run 45473007901. The later artifact set from run 45600944022 was separately detached-verified by [run 45601831710](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601831710); G7 is Pass for both exact sets. Run 45600944022 has not been validated by exact-source G9.42. All 20 task/backend outcomes remain Insufficient evidence; no backend ranking or automatic selection is authorized; `production_approval=false`.


## 16. G7 detached verification of the latest five-backend artifact set — 2026-11-25

The E.8.5/E.8.8 artifacts from [run 45600944022](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45600944022), exact source `ed33bf68c49fd41506d5d7917fbdc77bf8e544e7`, were downloaded by exact artifact ID and detached-verified in [run 45601831710](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601831710). The verifier ran 12 adversarial unit tests, recomputed archive byte counts and SHA-256 values, and checked report schema, source/run/attempt identity, backend/library/native-mode, E.8.5/E.8.8 parity/query telemetry, projection round-trip, repository snapshot, source hashes, context telemetry, side-effect declarations, SciPy hybrid representation and SNAP image/policy/deadlines.

All five archives and their embedded reports passed. The committed machine-readable dossier is `evidence/m74-e85-e88-run-45600944022/verified-dossier.json`; see [the run-specific dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier-45600944022.md). **G7 is Pass for the exact run 45600944022 artifact set.** This is detached byte/digest and report-consistency verification, not historical workflow re-execution or physical-runner attestation.

Run 45600944022 also passed the five-backend M7.4 task suite, E.8.5/E.8.8 and bounded G4 repository side-effect/snapshot-race tests. G4 remains Partial because atomic repository-wide snapshot semantics, Windows reparse-point path-opening TOCTOU, full external side-effect coverage and all mutation/restoration windows remain unresolved. G5/G6 and PATH/IMPACT domain qualification remain open. Exact-source G9.42 has not been run against this source. All 20 task/backend outcomes remain Insufficient evidence; `production_approval=false`.


## 17. Latest source: Windows handle-bound race test, five-backend regression and detached G7 — 2026-11-25

**Exact Stage1 source:** `0b37e79c9942e483cea770fc96138c4f185753e1`

### 17.1 G4 Windows source-reader result

[G4 run 45602554567](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554567) passed both the source-snapshot cost characterization job and the Windows compatibility job. Windows job `139165068194` ran the G4 source-snapshot, mutation and repository-side-effect suites on Windows Server 2022 with Python 3.11.9: **28 passed, 46 expected skips**. The new adversarial test swaps a normal in-root directory for an outside junction after component inspection and verifies that the opened file handle's final path is rejected.

The implementation binds reads to a held repository-root handle and a candidate file handle, rejects final reparse-point files, compares normalized final paths via `GetFinalPathNameByHandleW`, and reads from the same handle after containment succeeds. This closes the tested junction-replacement-to-outside schedule; it does not prove every Windows namespace/reparse-point case or an atomic repository-wide snapshot.

### 17.2 Latest five-backend acceptance

[E.8.5/E.8.8 run 45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671) passed all five backend jobs and aggregate summary `139165860984`. Each backend reported 21 M7.4 task-acceptance passes, 14/14 E.8.5 parity-verified queries and 43/43 E.8.8 parity-verified queries, with zero query/parity failures.

- G4 snapshot/mutation tests: 7 passed / 33 expected skips for NetworkX, SciPy, igraph and graph-tool; 8 passed / 32 expected skips for SNAP.
- G4 repository-side-effect/snapshot-race tests: 7 passed / 15 expected skips for the four in-process backends; 8 passed / 14 expected skips for SNAP. The extra skip is the Windows-only junction test, exercised by the Windows job above.
- SNAP additionally passed six worker protocol/restriction tests, one live Docker timeout/cleanup test and two resource-teardown tests.
- The Windows helper change is platform-specific; the five Linux backend jobs verify that the shared code remains importable and that their existing source-read paths and semantic reports remain correct.

### 17.3 Detached G7

The five artifacts from run 45602554671 were independently detached-verified by [run 45602963647](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647). Exact artifact IDs, byte counts and archive SHA-256 values matched the pinned manifest; embedded E.8.5/E.8.8 schemas, source/run/attempt identities, native modes/library versions, parity telemetry, repository graph/source identities, context operations, side-effect declarations, SciPy hybrid representation and SNAP worker image/policy/deadlines passed.

The machine-readable dossier is `evidence/m74-e85-e88-run-45602554671/verified-dossier.json`; see [the detailed dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier-45602554671.md). **G7 is Pass for this exact artifact set.** This is detached archive-byte/digest and report-consistency verification, not historical workflow re-execution or physical-runner attestation.

**Current decision:** G4 is improved but remains Partial because repository-wide snapshot atomicity, hard-link/metadata and external-side-effect coverage, remaining mutation/restoration schedules, and native projection postflight-to-return concurrency are unresolved. G5/G6 and PATH/IMPACT domain qualification remain open. Exact-source G9.42 has not been run against this source. All 20 task/backend outcomes remain Insufficient evidence; `production_approval=false`.


## 18. Windows handle-bound G4 race mitigation and latest exact-source evidence — 2026-11-25

**Exact Stage1 source:** `0b37e79c9942e483cea770fc96138c4f185753e1`

### 18.1 Windows G4 race test

[G4 run 45602554567](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554567) passed the source-snapshot cost characterization and Windows compatibility jobs. Windows job `139165068194` passed **28 tests with 46 expected skips**. The new adversarial test replaces an ordinary in-root directory with a junction to an outside directory after component inspection and before opening the candidate file. The handle-bound final-path check rejected the outside target.

The Windows reader now opens/holds the root handle, opens the candidate with `FILE_FLAG_OPEN_REPARSE_POINT`, rejects a final reparse point, compares normalized final paths from `GetFinalPathNameByHandleW`, and reads from the same handle with before/after descriptor identity checks. The first attempt failed only because the fixture's inside/outside payloads differed in length; the fixture was corrected before the passing run. The mitigation closes the tested junction-replacement schedule, not all Windows namespace, reparse-point, hard-link, volume or permission configurations.

### 18.2 Five-backend run and G7

[E.8.5/E.8.8 run 45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671) passed all five backend jobs and the aggregate summary. Each backend reported 21 M7.4 task-acceptance passes, E.8.5 14/14 parity and E.8.8 43/43 parity, with zero query/parity failures. The G4 snapshot/mutation and repository-side-effect suites passed for all backends; SNAP also passed worker protocol, live Docker timeout/cleanup and teardown tests.

The exact five artifact archives were detached-verified in [run 45602963647](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647). Artifact IDs, byte counts and SHA-256 values matched the pinned manifest; report schemas and source/run/attempt identities, native modes, versions, parity telemetry, graph/source snapshot identity, context telemetry, side-effect declarations, SciPy hybrid semantics and SNAP worker identity/policy/deadlines passed. The committed machine-readable dossier is `evidence/m74-e85-e88-run-45602554671/verified-dossier.json`; see [the detailed dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier-45602554671.md). **G7 is Pass for this exact set.**

**Current status:** G4 is improved but remains Partial because repository-wide snapshot atomicity, complete filesystem metadata/external-side-effect coverage, hard-link aliasing, arbitrary mutation/restoration schedules and native projection postflight-to-return concurrency remain unresolved. G5/G6 and PATH/IMPACT task-domain qualification remain open. Exact-source G9.42 has not been run against this SHA. All 20 task/backend outcomes remain Insufficient evidence; `production_approval=false`.


## 19. Current M7.4 status after domain-shaped workload, detached task evidence and M7.1 environment correction — 2026-11-26

This section supersedes earlier statements in Sections 14–18 that G5/G6 were wholly open. It does not supersede their run-specific evidence records or the explicit G4 limitations.

### 19.1 Exact-source task workload and G7

- E.8.5/E.8.8 plus M7.4 task suite: [run 45773593165](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45773593165), source `e15c18b1506fb9c4d4c71b6435eb1c42aa7ac187`.
- Each of five backends passed 22 M7.4 task tests, with 88 expected skips for the other backend partitions, zero failures and zero errors.
- The new FEM repository-shaped fixture exercises structural, dependency, path-to-evidence and impact operations with source/module/symbol/test/workflow/evidence node types and an explicit dependency cycle.
- Each backend artifact includes its JUnit XML report. The detached verifier checks 110 cases, 22 passes, 88 skips, zero failures/errors, and binds every passing test name to the backend in the archive.
- Detached G7 verification: [run 45774121550](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45774121550), artifact 15095590785. G7 is Pass for the exact run 45773593165 artifact set. See [run-specific dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier-45773593165.md).

G5 is **Partial**, not Pass: the new fixture is task-shaped and domain-relevant, but remains small and deterministic. Larger full-repository and problem-driven task workloads are still required before task/backend suitability can be concluded.

### 19.2 G6 CI execution envelope

M7.1 [run 45774182880](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45774182880), source `5d6d4089edc5b147f5e94e0364330acf09780113`, passed all five backend jobs and the aggregate summary. Each backend ran seven fixed smoke queries with two warm-ups and five measured repetitions; the reports include integrity-audit timings, query samples, engine construction, native adjacency telemetry, environment and worker provenance.

The graph-tool CPU compatibility defect was corrected: graph-tool now resolves to the generic x86-64 `_100` build after a fresh solve with `CONDA_OVERRIDE_ARCHSPEC=x86_64`; the workflow disables the stale environment cache and asserts the build. The earlier `_400` build caused SIGILL on an AMD EPYC 7763 runner because it was built for x86-64 microarchitecture level 4. The E.8.5/E.8.8 graph-tool job also passed with the generic build.

G6 is **Pass for the tested CI execution envelope**. This is not a production deployment qualification: representative task-level cost at larger sizes, peak memory, controlled runner variance and deployment-specific resource limits remain uncharacterized. See [M7.1 integrity-cost report](AE-32C-M7.1-Integrity-Cost-Smoke-2026-11-26.md).

### 19.3 Current gate matrix

| Gate | Current status | Basis / remaining boundary |
|---|---|---|
| G1 — Task definition | Pass | Four public graph-analysis task identities and query envelopes are specified |
| G2 — Semantic correctness | Pass for bounded fixtures | Independent expected-result and adversarial cases; not an exhaustive domain corpus |
| G3 — Public-path execution | Pass for tested paths | Native API instrumentation and reference parity in exact five-backend runs |
| G4 — Snapshot and mutation safety | **Partial** | Tested file/path/side-effect cases pass; repository-wide point-in-time atomicity, ABA schedules, all namespace aliases and projection postflight-to-return concurrency remain open |
| G5 — Task workload | **Partial** | Generic seeded topologies plus small FEM repository-shaped four-task fixture; larger full-repository and problem-driven workloads remain |
| G6 — Environment and operations | Pass within tested CI envelope | Versions, runner/Python strata, generic graph-tool ISA build, SNAP worker image, timeouts/cleanup and smoke cost recorded; no production deployment qualification |
| G7 — Evidence integrity | Pass for cited exact sets | Detached archive and embedded JUnit/report verification for run 45773593165 |
| G8 — Scope discipline | Pass | No ranking, global score, automatic selection, scientific approval or production approval |

### 19.4 Decision matrix remains unchanged

All 20 task/backend pairs remain **Insufficient evidence**. G4 and G5 are mandatory and still partial; therefore no pair can be promoted to Suitable or Conditionally suitable. The five backends remain alternative computational options chosen by task relevance, not performance competitors. No ranking, automatic selector, scientific approval or production approval is authorized; `production_approval=false`.

The updated `validation/profiles/G9.42.yaml` now includes the M7.4 task suite, G4 snapshot/mutation tests, repository-side-effect tests and detached dossier tests. It has not yet been run against the current source revision; the five-backend E.8.5/E.8.8 workflows and detached G7 run above are separate evidence.

### 19.5 Out-of-scope architecture layers

This matrix covers graph traversal backends for the four public graph-analysis tasks only. It does not accept the pluggable LLM integration, remediation decision optimization, formal-solver portfolio or governed self-examination/termination layers. Each needs its own task contract, authority boundary, evidence model, tests and acceptance decision. Passing M7.4 does not imply acceptance of those layers or of the overall audit engine.

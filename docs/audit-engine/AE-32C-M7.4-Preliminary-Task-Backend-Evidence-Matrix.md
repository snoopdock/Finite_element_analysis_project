# AE-32C M7.4 — Preliminary Task/Backend Evidence Matrix

**Record type:** Preliminary evidence ledger; not a suitability approval  
**Branch:** stage1/section-uuids  
**Exact task-test source:** 51d025fd328b00a59988a05fe72d9092262434f5  
**Exact E.8.5/E.8.8 run:** [45395352748](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45395352748), attempt 1, success  
**Aggregate summary job:** 138450475726, success  
**Controlling contract:** [M7.4 Task-Specific Backend Suitability Assessment Contract](AE-32C-M7.4-Task-Suitability-Assessment-Contract.md)  
**Validation evidence:** [M7.4 Initial Task Assessment Validation](AE-32C-M7.4-Initial-Task-Assessment-Validation.md)  
**Authority:** production_approval=false; no global ranking, winner, automatic selection or runtime promotion.

---

## 1. Decision status

The expanded M7.4 acceptance module passed in all five backend environments. Each selected-backend job reported 21 passed and 84 intentionally skipped cases. This provides positive task-scoped semantic and native-path evidence for all 20 task/backend combinations (four public tasks × five backends).

**This is not yet 20 suitability approvals.** Under the M7.4 contract, an untested or only partially evidenced mandatory gate prevents a Suitable decision. The preliminary outcome for every pair below is therefore **Insufficient evidence**. The reason is not an observed parity failure; it is the remaining incompleteness in representative workload, mutation/corruption envelope, operational envelope and independent evidence closure.

The five backends are task-relevant computational options, not competing products. This record does not rank them.

## 2. Source and test evidence

The exact E.8.5/E.8.8 source SHA was 51d025fd328b00a59988a05fe72d9092262434f5. The task acceptance module was checked out at that exact source in all five backend jobs.

| Backend | CI job ID | M7.4 result |
|---|---:|---:|
| NetworkX | 138449745984 | 21 passed; 84 expected skips |
| SciPy | 138449746035 | 21 passed; 84 expected skips |
| python-igraph | 138449745936 | 21 passed; 84 expected skips |
| graph-tool | 138449746042 | 21 passed; 84 expected skips |
| SNAP isolated worker | 138449745692 | 21 passed; 84 expected skips |

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
| G7 — Evidence integrity | Exact source SHA, run/attempt, source/graph manifest hashes, artifact IDs and archive digests recorded | Partial | Detached verification pass over this exact evidence bundle is outstanding |
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
4. Complete G7 with a detached verifier pass over this exact source/run/artifact set.
5. Complete PATH domain-specific evidence/locator/source follow-through.
6. Keep IMPACT canonical SCC behavior explicit. Native SCC support would require a separate API/algorithm contract and parity evidence.
7. Run exact-revision G9.42 through the main-branch manual dispatcher, with branch stage1/section-uuids, profile G9.42 and regression mode profile, when an authorized workflow-dispatch capability is available. The profile contains the SNAP adapter, live Docker lifecycle, E.8.8 teardown and M7.4 workload tests. This record does not claim G9.42 has run.
8. Only after mandatory gates close should each pair receive one formal outcome from the contract vocabulary.

production_approval=false remains invariant.

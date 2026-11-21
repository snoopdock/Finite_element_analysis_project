# AE-32C M7 — Comparative Backend Performance and Promotion Policy

**Status:** M7 opened; protocol design and benchmark-gap analysis only. No performance winner is claimed and no backend is promoted.  
**Prerequisite acceptance snapshot:** Stage1 `81eb77aff35afe297a596a91826e016048515c0f`  
**Exact-source E.8.5/E.8.8 run:** [44917397347](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44917397347) — all five backends passed.  
**Exact-source G9.42 run:** [44917571217](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44917571217) — passed; 53 engine tests, 690 targeted tests, 3,629 regression tests.  
**Target branch:** `stage1/section-uuids` only.  
**Authority boundary:** `production_approval=false`; no automatic backend selection, scientific approval, or graph mutation.

---

## 1. Purpose and scope

M7 determines whether the five accepted native backend paths provide useful operational value for particular graph workloads:

- NetworkX — `networkx_successor_predecessor_adjacency`
- SciPy — `scipy_csr_csc_adjacency`
- python-igraph — `igraph_incident_edge_ids`
- graph-tool — `graph_tool_vertex_edge_iterators`
- SNAP 6.0 — `snap_isolated_worker_tneanet_edge_ids`

M7 is downstream of semantic correctness. It does not reopen accepted M1–M6 contracts unless a benchmark exposes a correctness defect. It does not establish scientific truth or diagnostic quality.

This is the AE-32C backend-roadmap **M7**, not a renumbering of the repository's earlier G6 benchmarking sequence or the original G7 Semantic Reasoning Rules milestone. Existing G6.1/G6.2 artifacts remain historical evidence and are inputs to the gap analysis, not sufficient five-backend M7 acceptance.

## 2. Baseline and benchmark gap

The existing `backend_benchmark.py` / `backend_benchmark_campaign.py` infrastructure is valuable but currently benchmarks only NetworkX and SciPy. Its common operation is directed reachability over adapter exports. It measures projection construction and a reachability batch, validates useful structural parity, and produces bounded multi-seed descriptive summaries.

It does **not** yet provide an apples-to-apples comparison of all five accepted paths:

1. graph-tool, igraph and SNAP are absent from the benchmark adapter matrix;
2. the existing NetworkX and SciPy query functions use exported graph/matrix representations rather than the accepted per-node native adjacency API used by the M1–M6 traversal path;
3. the current benchmark does not separately account for one-time projection validation, worker startup/IPC, traversal, evidence reconstruction and full context-tool latency;
4. its SciPy CSR storage byte count is not comparable to total process memory for the other backends;
5. its current synthetic topology profiles do not isolate all requested sparse/dense, degree-skew and bound distributions;
6. its existing multi-seed campaign explicitly treats measurements as descriptive and does not establish independent hardware-population trials.

Therefore, M7 must extend the measurement design without retroactively treating G6.1/G6.2 timing data as evidence for graph-tool, igraph or SNAP.

## 3. Benchmark invariants

Every timing comparison must satisfy these invariants:

- **Same canonical input:** each backend receives the same immutable `SemanticGraph` snapshot for a given workload ID and graph digest.
- **Same semantic query:** query direction, relation filters, traversal bounds, ordering, stop conditions and result projection are identical.
- **Parity before timing:** exact projection/occurrence validation and independent reference parity pass before a sample is admitted.
- **Native-path proof:** runtime telemetry identifies the expected native query mode and records adjacency lookups and edge occurrences read. A fallback or non-native run is rejected, not silently timed as native.
- **Separate preparation and query costs:** graph generation, fixture verification and parity work are not hidden inside query-only measurements. Construction, projection validation and query costs are reported separately.
- **Worker cost is visible:** SNAP cold worker/container startup, graph transfer/initialization, warm IPC request latency and native query time are separate metrics. End-to-end SNAP latency must include the IPC/serialization costs incurred by a real caller.
- **Memory is comparable:** report process-level peak RSS for the host and, separately, the SNAP worker. Do not compare SciPy CSR array bytes with total RSS of another backend as if they were equivalent.
- **Raw data retained:** preserve raw samples, workload definitions, environment details, query outputs/digests, telemetry and report digests for independent analysis.
- **No cross-environment winner:** results from different CPU models, runner images, architectures, package versions or materially different load conditions are not ranked as if they were controlled.
- **No authority escalation:** timing results never enable backend auto-selection or scientific/production approval.

## 4. Workload matrix

Use deterministic workload manifests with explicit graph digests and seeded generators. Each workload family should cover:

| Dimension | Required cases |
|---|---|
| Scale | Small, medium, large; include current G6.1 sizes for continuity and larger bounded cases where all adapters can safely run |
| Density | Sparse and relatively dense directed graphs |
| Degree distribution | Uniform/low-degree, hub-heavy and skewed/high-degree |
| Topology | Cyclic, disconnected/isolated nodes, long paths, branching and strongly connected regions |
| Occurrences | Parallel edges, repeated endpoint/relation combinations and self-loops |
| Query bounds | Shallow/deep traversal, small/large visited-node limits and early truncation |
| Direction | OUT, IN and BOTH |
| Filtering | Relation-filtered and unfiltered queries |

A workload is not defined by node/edge counts alone. Its manifest must include generator version, seed, topology parameters, expected edge-occurrence counts, query matrix and canonical graph SHA-256.

Use a common query corpus for all backends. At minimum it must include native adjacency access and the shared graph traversal operations. Repository-context operations (`trace_execution_context`, `find_workflow_context`, and nested workflow context) should be a separate integration workload because they include repository evidence reconstruction and domain-specific processing.

## 5. Measurement model

For each backend/workload/query, collect:

1. adapter construction time;
2. projection and one-time validation time;
3. projection memory / peak RSS delta;
4. native adjacency lookup count;
5. native edge occurrences inspected/read;
6. traversal time excluding evidence serialization;
7. evidence/result reconstruction time;
8. backend-call and serialization overhead;
9. end-to-end query latency;
10. cold-start and warm-query latency where process boundaries exist.

Report raw observations and descriptive median, p95, minimum, maximum and median absolute deviation (MAD). Use multiple distinct deterministic graph seeds and repeated timing observations per seed. Keep seed-level and repetition-level data rather than flattening all observations into a single nominal sample.

Run backends sequentially on the same runner class where possible; randomize or rotate backend order across repeated blocks to reduce systematic order/cache bias. Record CPU model, OS image, architecture, Python version, backend versions, native library versions, worker image digest, dependency lock/fingerprint and run load context. If the runner environment cannot be held constant, split results into environment-specific strata and do not calculate a single cross-stratum ranking.

No fixed nanosecond threshold is an acceptance gate. Correctness and native-path proof are hard gates; timing is descriptive evidence.

## 6. SNAP-specific accounting

SNAP runs behind the isolated CPython 3.9 worker while the orchestrator remains on Python 3.11. The benchmark must distinguish:

- image availability/build time (not a per-query runtime metric);
- worker process/container startup;
- graph serialization and transfer;
- TNEANet construction and projection audit;
- warm JSON-lines request/response and IPC overhead;
- native TNEANet adjacency traversal;
- host-side canonical occurrence validation and result reconstruction;
- end-to-end query latency.

The worker image digest, SNAP version, worker Python version and declared container restrictions must be included in every report. Never compare only the native C++ adjacency time with another backend's full public API call; report both native-operation and caller-visible end-to-end costs.

## 7. Statistical and interpretive limits

The initial campaign is a controlled engineering benchmark, not a population-level performance study. Distinct graph seeds vary graph topology; they do not create independent samples of hardware, operating systems or runner load. Repeated timings on one ephemeral runner remain correlated observations.

M7 may report workload-specific observed ratios and robust descriptive summaries. It must not claim statistical significance, universal superiority, asymptotic complexity from a few finite sizes, or a hardware-independent winner. Any later inferential analysis requires a separately justified experimental design and independent hardware/run replication.

## 8. Promotion policy

A backend can be considered for a task only if:

- M1–M6 correctness/compatibility gates remain accepted for the exact implementation snapshot;
- the relevant workload/query parity and native-path instrumentation pass;
- resource and operational costs are reported, including worker isolation/IPC where applicable;
- the benchmark evidence is reproducible and environment-matched;
- the task-specific policy states why its trade-offs are acceptable.

M7 does not itself change the registry's production approval state. Any later promotion requires a separate explicit decision, scoped by backend, task, runtime environment and rollback policy. No single backend is assumed to win all workloads.

## 9. Implementation sequence and exit gates

**M7.0 — Baseline freeze and gap analysis (current):**
- record M5/M6 exact-source acceptance evidence;
- inspect G6.1/G6.2 code, tests and workflow constraints;
- define workload, measurement, telemetry and authority contracts;
- identify existing native instrumentation that can be reused without changing adapter semantics.

**M7.1 — Backend-neutral benchmark harness:**
- add a harness over the five already-accepted adapters;
- consume immutable canonical graph fixtures and a shared query manifest;
- reject missing parity, missing native telemetry or backend fallback;
- separate setup, validation, traversal, reconstruction and end-to-end timing.

**M7.2 — Controlled workload and campaign runner:**
- add bounded graph topology/scale families and multi-seed repeated measurements;
- run sequentially or with controlled order on equivalent runner environments;
- capture process and worker memory, environment, raw samples and digests.

**M7.3 — Independent verifier and analysis:**
- reconstruct workload manifests and expected results;
- verify embedded child reports, telemetry, query parity, sample counts and aggregate mathematics;
- reject rehashed altered summaries, mixed environment strata and injected winner/approval fields.

**M7.4 — Benchmark dossier and task-specific policy:**
- publish the reproducible dossier, limitations, observed trade-offs and unresolved gaps;
- state per-task eligibility without automatic backend selection;
- preserve `production_approval=false` unless a separate authorized approval explicitly changes it.

**M7 exit:** all five backend reports are parity-verified and demonstrate the expected native path; benchmark reports are independently verifiable; resource/cold/warm costs and environment strata are explicit; a task-specific policy is documented; no universal winner or unauthorized approval is asserted.

---

## 10. Acceptance references

- G6.1 implementation: `audit_engine/semantic_audit/graph/backend/backend_benchmark.py`
- G6.2 campaign: `audit_engine/semantic_audit/graph/backend/backend_benchmark_campaign.py`
- G6.1 design: `docs/architecture/G6_01_Graph_Backend_Benchmarking.md`
- G6.2 acceptance: `docs/architecture/G6_02_Multi_Seed_Benchmark_Acceptance.md`
- M5/M6 native conformance: [E.8.5/E.8.8 run 44917397347](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44917397347)
- Exact-commit validation: [G9.42 run 44917571217](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44917571217)
- GitHub workflow-dispatch behavior: [GitHub Actions manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

The run artifacts are retained as evidence of correctness and native execution, not as performance measurements.

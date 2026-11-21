# AE-32C M7 — Task Suitability and Operational Characterization

**Status:** M7.0 protocol/gap analysis complete. M7.1 five-backend native smoke validation passed in [run 44937517812](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44937517812). M7.2 task-suitability workload generator, per-backend campaign runner, verifier and tests are committed; exact-source G9.42 validation and the five-backend campaign execution remain pending.  
**M7.1 workflow revision:** `main` SHA `182d0009f1c759c46813e3a1cbbf34d22c247acb`  
**M7.1 benchmark source:** Stage1 SHA `342c9d55b1dc49ccf93759d0dce203723485ef17`  
**M7.2 implementation:** `tools/gb06_task_suitability_campaign.py`  
**M7.2 tests:** `tests/semantic_graph/test_m72_task_suitability_campaign.py`  
**Current M7.2 Stage1 implementation head:** `2638c9cda2acaf5b26b29c427f662f9c921a1176`  
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
- **M7.2 — Task-suitability workload families and bounded multi-seed campaign:** initial implementation committed; exact-source validation and five-backend campaign execution pending.
- **M7.3 — Detached report verification and descriptive evidence dossier:** not started.
- **M7.4 — Task-specific suitability assessment and explicit policy:** not started.

## 10. Architectural references

- ADR-013 — Semantic Graph Backend Selection Policy.
- ADR-032 — Semantic Graph Computation Backend Boundary.
- `audit_engine/semantic_audit/graph/backend/adapter_interface.py`.
- `audit_engine/semantic_audit/graph/backend/capability_registry.py`.
- `tools/gb05_native_backend_performance_benchmark.py` — M7.1 smoke harness.
- `tools/gb06_task_suitability_campaign.py` — M7.2 seeded workload campaign.
- `tests/semantic_graph/test_m7_native_backend_performance_benchmark.py`.
- `tests/semantic_graph/test_m72_task_suitability_campaign.py`.
- `validation/profiles/G9.42.yaml` — deterministic validation profile.

Historical G6.1/G6.2 artifacts remain valid for their original NetworkX/SciPy exported-representation workloads. They are not substituted for M7 native-path or task-suitability evidence.

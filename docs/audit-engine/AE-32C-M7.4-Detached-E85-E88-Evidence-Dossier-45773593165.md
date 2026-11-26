# AE-32C M7.4 Detached E.8.5/E.8.8 and Task-Acceptance Dossier — Run 45773593165

**Campaign run:** [45773593165](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45773593165)  
**Detached verifier run:** [45774121550](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45774121550)  
**Branch:** `stage1/section-uuids`  
**Exact source revision:** `e15c18b1506fb9c4d4c71b6435eb1c42aa7ac187`  
**Run attempt:** 1  
**Manifest:** `docs/audit-engine/evidence/m74-e85-e88-run-45773593165/manifest.json`  
**SNAP worker image:** `sha256:59ed7b3811b5f22b572fc36f9dd74f3176244583dd9419b4ecdd27dfb80b80b9`

## 1. Result

<badge color="success">Detached verification passed</badge>

All five backend jobs and the aggregate E.8.5/E.8.8 workflow summary completed successfully. Each backend artifact contains:
- the E.8.5 native conformance report;
- the E.8.8 repository-context conformance report;
- `reports/m74-task-acceptance.xml`, the complete JUnit report for the M7.4 public-task acceptance module.

The detached verifier downloaded each archive by its exact Actions artifact ID, checked archive byte size and SHA-256 against the committed manifest, validated report/source/run/backend identities, validated E.8.5/E.8.8 semantic and telemetry contracts, and parsed the M7.4 JUnit XML.

## 2. Per-backend archive ledger

| Backend | Library version | Native query mode | Artifact ID | ZIP bytes | ZIP SHA-256 |
|---|---:|---|---:|---:|---|
| NetworkX | 3.6.1 | `networkx_successor_predecessor_adjacency` | 15094973420 | 4,450 | `db43c47924c62b4f11b8dbdbb42e64f25336d260312b7bc16ecfbdd52839aca1` |
| SciPy | 1.17.1 | `scipy_csr_csc_adjacency` | 15094968420 | 4,616 | `01259eaa9a4f5ffa7757b10fb881836dcd7ffa4b070cfcb6c21f53501eb97db1` |
| python-igraph | 1.0.0 | `igraph_incident_edge_ids` | 15094424934 | 4,429 | `53346fda47bed80ca878ce52015cb5bd6a3c630ad10e4c5c10dd282f60af76bb` |
| graph-tool | 3.9 | `graph_tool_vertex_edge_iterators` | 15095142068 | 4,555 | `415dc076edd3c00ced581659788d714ad64c05f46ff4ffa8dedf384e8395157f` |
| SNAP | 6.0.0 | `snap_isolated_worker_tneanet_edge_ids` | 15095470377 | 5,149 | `4b4373bd50bbb1d7867244c62f4f5fd79ec7882f5e4dfe94a18398337a94c3e8` |

## 3. M7.4 task-acceptance JUnit evidence

Each backend's JUnit XML contains 110 test cases:
- **22 passed** for the backend selected by that job;
- **88 skipped** because they target the other four backends;
- **0 failures**;
- **0 errors**.

The detached verifier checked that all 22 non-skipped test names in each archive bind to that archive's backend identity. It also checked the JUnit XML byte digest.

| Backend | JUnit SHA-256 |
|---|---|
| NetworkX | `5bf44df76c53a8eaf4a9bb55b315eec58395cf06bd7b5b402f941b8cc7c67b52` |
| SciPy | `93534d23b19cadcbdb6ea791ef0c7f58dfd04a6b47e81ebb214fb83df8d3892c` |
| python-igraph | `f84591540a95df1ef27c1568a3440d507104c9d17f3418d02a98f88b0dad3963` |
| graph-tool | `65acae6aac4ebff474ac93ff02eeba3209d60f80aea154fc971168647bc01ecf` |
| SNAP | `520a304d98fccf26800c4d6e04c93d9e3334f8dd6071337fa66328333b6f2890` |

The task module covers the public structural, dependency, path and impact analyzers. The added FEM repository-shaped fixture includes source files, modules, a material-property symbol, a supporting documentation evidence record, test and workflow nodes, and a dependency cycle. It asserts reference parity, native execution, expected task semantics and no mutation of the canonical graph.

## 4. E.8.5 and E.8.8 conformance

Every backend reported:
- E.8.5: 7 cases, 14/14 parity-verified queries, zero query failures and zero parity failures.
- E.8.8: 43/43 parity-verified repository-context queries, zero query failures and zero parity failures.
- E.8.5 native adjacency telemetry: 34 lookups and 96 edge occurrences read.
- E.8.8 native adjacency telemetry: 45 lookups and 86 edge occurrences read.
- Context parity: 7 `trace_execution_context`, 16 `find_workflow_context`, and 16 nested workflow-context operations.

Shared repository evidence:
- 26 graph nodes, 41 graph edges, 9 indexed files.
- Evidence index status: `complete`.
- Source manifest SHA-256: `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`.
- E.8.5 graph fingerprint: `graph:c6146d2473910927d9c7f113d92a4400`.
- E.8.8 graph fingerprint: `graph:1aca2caea6acabcf695a6118f7202b6e`.

SciPy's result remains a hybrid CSR/CSC topology implementation with semantic edge-occurrence side channels; the sparse matrices alone are not treated as a lossless semantic multigraph. SNAP remains an isolated CPython 3.9 worker; this dossier does not establish an in-process Python 3.11 SNAP adapter.

## 5. Detached verifier provenance

Detached workflow artifact:
- ID: `15095590785`
- Name: `m74-detached-dossier-45773593165`
- Size: 2,509 bytes
- ZIP SHA-256: `7a00295967aa12c992704434acd0e0640e7c0adfb459a6e353d79f7438a88c93`

Verifier implementation SHA-256: `0565c90efccb2e3d1a660023f8c96c40bda335d855f9be3c748d9fb43ec89000`  
Manifest SHA-256: `b8e40e4c9b052f12a308499a650b87eab6e847c20050b6c269ca9443ca0d5bdd`

The detached verifier's adversarial unit tests passed before it downloaded and checked the exact campaign archives. The machine-readable verified dossier is preserved in the detached Actions artifact.

## 6. Acceptance interpretation

**G7 is Pass for this exact five-backend artifact set**, including the M7.4 task-level JUnit reports. This proves the recorded artifact bytes and declared report contracts are consistent with the pinned run and source revision. It is not a historical workflow re-execution or physical-runner attestation.

The FEM graph is a deterministic domain-shaped fixture, not a full-scale production repository workload. G5 evidence is stronger but does not by itself establish task/backend suitability. G4 remains Partial because atomic repository-wide snapshot semantics, broader filesystem namespace and side-effect coverage, mutation/restoration schedules and native projection postflight-to-return concurrency remain unresolved. G6 remains a separate integrity-cost and environment qualification gate.

All 20 task/backend outcomes remain **Insufficient evidence** until the remaining mandatory gates and representative workload evidence are satisfied. The libraries remain alternative computational options, not competitors; no ranking or automatic selector is authorized. `production_approval=false`.

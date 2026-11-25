# AE-32C M7.4 — Detached E.8.5/E.8.8 Evidence Dossier

**Status:** Verified  
**Source workflow:** [E.8.5/E.8.8 run 45473007901](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007901), attempt 1  
**Detached verifier workflow:** [run 45601021689](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601021689)  
**Tested source:** `stage1/section-uuids` at `098a87394d972010f04466c540fcf5f43b490f9b`  
**Detached verifier revision:** `8efd78d6e5bb6327be083d0f09e885122707f56d`

## Method and scope

The detached workflow downloaded all five historical Actions ZIP archives by the exact artifact IDs pinned in [the manifest](evidence/m74-e85-e88-run-45473007901/manifest.json). It recomputed archive sizes and SHA-256 digests, then checked the two report members in each ZIP, archive-member safety, report schemas, source/run/attempt provenance, backend/library/native-mode identity, E.8.5 and E.8.8 semantic case and query contracts, parity telemetry, projection round-trip, repository snapshot identity, context-operation telemetry, source-file hashes, side-effect declarations, SciPy's hybrid representation and SNAP worker restrictions.

The workflow also ran the verifier's adversarial unit suite successfully before downloading the artifacts. The verifier implementation was `tools/gb08_m74_native_conformance_dossier.py`, SHA-256 `8b7aa5b42675126ee92324ae2744c5ad31202725e27240d5a938e6b4ad724c3b`. The manifest SHA-256 was `00514ec1c37593651af67e575e58cd594b725833604d86be160877c0d7cc4c3f`. Verification ran under Python 3.11.18.

The machine-readable verified result is the [detached dossier artifact](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601021689/artifacts/15015925967), artifact ID `15015925967`, 2,210 bytes, Actions-reported ZIP SHA-256 `814e03f4fd018acc27a963c1db8d7e56f9c71cf281cb13c15fd1a710b5b83fb6`.

## Backend evidence

| Backend | Artifact ID | ZIP bytes | Archive SHA-256 | Library | Native query mode | E.8.5 / E.8.8 parity |
|---|---:|---:|---|---|---|---:|
| NetworkX | 14957483338 | 2,770 | `405d08ecf84037da757b1a810d619b184d00d71009817537cd0a89686b073f16` | 3.6.1 | `networkx_successor_predecessor_adjacency` | 14/14; 43/43 |
| SciPy | 14956708544 | 2,929 | `16814cdcea9fde5460170d3cb8baecd348d674fb3551ebf14cf78c855e6e0076` | 1.17.1 | `scipy_csr_csc_adjacency` | 14/14; 43/43 |
| python-igraph | 14959140093 | 2,749 | `644996cad98dec296072f5adc2d04168ff7bddbb333847ffd436dfebca96e9fd` | 1.0.0 | `igraph_incident_edge_ids` | 14/14; 43/43 |
| graph-tool | 14956094000 | 2,846 | `a14b0c980cbb3b48ac4543f8991bd90788db2b87549a76d1cfcaf282aad48e84` | 3.9 | `graph_tool_vertex_edge_iterators` | 14/14; 43/43 |
| SNAP | 14956883659 | 3,429 | `f9353cf1f20951e236d1ea37c1918d2e071e86d248c01e677308c532caddf0f9` | 6.0.0 | `snap_isolated_worker_tneanet_edge_ids` | 14/14; 43/43 |

For every backend, E.8.5 recorded seven conformance cases and 14/14 parity-verified queries, with 34 native adjacency lookups and 96 native edge occurrences read. E.8.8 recorded 43/43 parity-verified queries, with 45 native adjacency lookups and 86 native edge occurrences read. Query failures and parity failures were zero in both reports.

The common E.8.8 repository snapshot was 26 nodes, 41 edge occurrences and 9 indexed files; graph fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`; source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. Context parity was 7/7 for trace execution, 16/16 for workflow context and 16/16 for nested workflow context. The two graph-to-source reads (`main.py` and `tests/checks.py`) matched their expected SHA-256 hashes.

SNAP used worker image `sha256:a6feacb4726070cb6e990ad13a7b4aefe557b6ebfae7adc3431c92af1d8e9ec2`, Python 3.9.25 and SNAP 6.0.0. E.8.5 enforced a 120-second request timeout; E.8.8 enforced 30 seconds. The E.8.8 report verified network disabled, read-only root filesystem, no writable mounts, all capabilities dropped, no repository mount, no provider credentials, 512 MiB memory, one CPU and 64-PID limit. SciPy remains correctly described as a hybrid CSR/CSC topology representation plus exact semantic side channels, not as a complete semantic graph encoded in the sparse matrices alone.

## G7 conclusion

**G7 — Evidence integrity: Pass for the exact five-backend E.8.5/E.8.8 artifact set from run 45473007901.**

The detached verifier bound the five nonexpired ZIPs to exact artifact IDs, sizes, archive digests, workflow run/attempt, branch and source SHA. It checked the embedded report contracts and cross-backend invariants and emitted a verified machine-readable dossier.

This is detached artifact-byte/digest and report-consistency verification. It does **not** rerun the historical workflows, independently reproduce the physical runner environments, or provide signed runner attestation. The dossier's hashes are integrity identifiers, not cryptographic signatures.

G7 closure does not close G2, G4, G5 or G6 and does not establish task-domain suitability. In particular, G4 remains Partial; the Windows path-opening race and repository-wide atomic-snapshot boundary remain unresolved. Representative audit-domain workload and operational-cost qualification also remain open. PATH claim-to-evidence source follow-through and the hybrid IMPACT canonical-graph SCC boundary remain separately scoped.

All 20 task/backend outcomes remain **Insufficient evidence**. No global ranking, performance winner, automatic selector, scientific approval, runtime promotion or production approval is inferred. `production_approval=false` remains invariant.

# AE-32C M7.4 — Detached E.8.5/E.8.8 Evidence Dossier

**Status:** Verified  
**Source workflow:** [E.8.5/E.8.8 run 45600944022](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45600944022), attempt 1  
**Detached verifier workflow:** [run 45601831710](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601831710)  
**Tested source:** `stage1/section-uuids` at `ed33bf68c49fd41506d5d7917fbdc77bf8e544e7`  
**Verifier workflow revision:** `974922a6d492c3d2d97f96d8ae99dfd17c7b80dd`

## Method and scope

The detached workflow ran the verifier's adversarial unit suite (12 tests; all passed), downloaded the five original Actions ZIP archives by the exact artifact IDs pinned in [the manifest](evidence/m74-e85-e88-run-45600944022/manifest.json), recomputed archive sizes and SHA-256 digests, and checked the two report members in each archive. The verifier bound each report to its schema, backend, source revision, run/attempt and workflow identity; checked native query modes and library versions; validated the E.8.5/E.8.8 case/query/parity and telemetry contracts; and checked projection round-trip, repository snapshot identity, context telemetry, source-read hashes, side-effect declarations, SciPy's hybrid representation and SNAP worker restrictions.

The verifier implementation was `tools/gb08_m74_native_conformance_dossier.py`, SHA-256 `8b7aa5b42675126ee92324ae2744c5ad31202725e27240d5a938e6b4ad724c3b`. The manifest SHA-256 was `3c1f11fa39ed73e215d67c9cab3d73a362686842661f6d6685a4c3d34909cdbc`. Verification ran under Python 3.11.18.

The verified machine-readable dossier is committed at [`evidence/m74-e85-e88-run-45600944022/verified-dossier.json`](evidence/m74-e85-e88-run-45600944022/verified-dossier.json) and preserved as [Actions artifact 15014489921](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601831710/artifacts/15014489921), 2,209 bytes, ZIP SHA-256 `792aea796cc6cf73f8b1ec34dc230c01f0ec3e411b53897fbfd83b1442920a95`.

## Backend evidence

| Backend | Artifact ID | ZIP bytes | Archive SHA-256 | Library | Native query mode |
|---|---:|---:|---|---|---|
| NetworkX | 15015546978 | 2,767 | `a1e85f0fc21249d25cb0eb3b46b912c889a866898bf5c48c10409ca541bfcd8a` | 3.6.1 | `networkx_successor_predecessor_adjacency` |
| SciPy | 15015397170 | 2,927 | `3b68803963ef8708c26b6ef14d0330782e4fd8a4fc84af2e18e8f14bba163bcb` | 1.17.1 | `scipy_csr_csc_adjacency` |
| python-igraph | 15013799761 | 2,747 | `7b37eceabbf316e5927c3af34f37502c772ca7a8161e223ca17204ad74658fbd` | 1.0.0 | `igraph_incident_edge_ids` |
| graph-tool | 15016215025 | 2,843 | `32d33b8b858b86e121f7491df30fbb9c12b4762d35f9166aa78c37d3919bbb37` | 3.9 | `graph_tool_vertex_edge_iterators` |
| SNAP | 15014649334 | 3,435 | `abd715bd0e05e65b13b53a68b18f143788f14471a19d8e94ae1c7ce823b440d4` | 6.0.0 | `snap_isolated_worker_tneanet_edge_ids` |

Each backend passed seven E.8.5 cases and 14/14 parity-verified queries, with 34 native adjacency lookups and 96 native edge occurrences read. Each E.8.8 report passed 43/43 parity-verified queries, with 45 native adjacency lookups and 86 native edge occurrences read. Query failures and parity failures were zero in both reports.

The common E.8.8 repository snapshot was 26 nodes, 41 edge occurrences and 9 indexed files; graph fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`; source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. Context parity was 7/7 for trace execution, 16/16 for workflow context and 16/16 for nested workflow context. The two graph-to-source reads (`main.py` and `tests/checks.py`) matched their recorded SHA-256 hashes.

SNAP used worker image `sha256:ef460791e7e5fcf6c7d7b232941cca37ea6020704454bee2c685aec1d094bd14`, Python 3.9.25 and SNAP 6.0.0. E.8.5 enforced a 120-second request timeout; E.8.8 enforced 30 seconds. The E.8.8 report verified network disabled, read-only root filesystem, no writable mounts, all capabilities dropped, no repository mount, no provider credentials, 512 MiB memory, one CPU and 64-PID limit. SciPy remains correctly described as a hybrid CSR/CSC topology representation plus exact semantic side channels.

## G7 conclusion

**G7 — Evidence integrity: Pass for the exact five-backend E.8.5/E.8.8 artifact set from run 45600944022.**

The detached verifier matched all five original ZIPs to the pinned artifact IDs, sizes and archive digests, then validated report provenance and declared semantic contracts. The detached result is not an inference from the source workflow's green status: it is a separate workflow and artifact set.

This is detached archive-byte/digest and report-consistency verification. It does **not** rerun the historical workflows, independently reproduce the physical runner environments, or provide signed runner attestation. Hashes are integrity identifiers, not cryptographic signatures.

The latest source also passed the five-backend E.8.5/E.8.8 regression and bounded G4 repository side-effect/snapshot-race tests (see [run 45600944022](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45600944022)). Those test results strengthen G4 evidence but do not make the repository snapshot atomic: Windows reparse-point path-opening TOCTOU, all external filesystem side effects, arbitrary mutation/restoration schedules and postflight-to-return races remain unresolved.

All 20 task/backend suitability outcomes remain **Insufficient evidence**. No global ranking, performance winner, automatic selector, scientific approval, runtime promotion or production approval is inferred. `production_approval=false` remains invariant.

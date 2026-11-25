# AE-32C M7.4 — Detached E.8.5/E.8.8 Evidence Dossier

**Status:** Verified  
**Source workflow:** [E.8.5/E.8.8 run 45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671), attempt 1  
**Detached verifier workflow:** [run 45602963647](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647)  
**Tested source:** `stage1/section-uuids` at `0b37e79c9942e483cea770fc96138c4f185753e1`  
**Verifier workflow revision:** `1d47738f5837c4f0ccf85331be5afb7cc9cd47f3`

## Method and scope

The detached workflow ran the verifier's adversarial unit suite, downloaded the five original Actions ZIP archives by the exact artifact IDs pinned in [the manifest](evidence/m74-e85-e88-run-45602554671/manifest.json), recomputed archive sizes and SHA-256 digests, and checked the two report members in each archive. It bound each report to its schema, backend, source revision, run/attempt and workflow identity; checked native query modes and library versions; validated the E.8.5/E.8.8 case/query/parity and telemetry contracts; and checked projection round-trip, repository snapshot identity, context telemetry, source-read hashes, side-effect declarations, SciPy's hybrid representation and SNAP worker restrictions.

The verifier implementation was `tools/gb08_m74_native_conformance_dossier.py`, SHA-256 `8b7aa5b42675126ee92324ae2744c5ad31202725e27240d5a938e6b4ad724c3b`. The manifest SHA-256 was `8ed07712e0b32cadda4684dfc75acd83557b092f2a5d0c7a4862d77d6c2d7adc`. Verification ran under Python 3.11.18.

The verified machine-readable dossier is committed at [`evidence/m74-e85-e88-run-45602554671/verified-dossier.json`](evidence/m74-e85-e88-run-45602554671/verified-dossier.json) and preserved as [Actions artifact 15016676849](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647/artifacts/15016676849), 2,207 bytes, ZIP SHA-256 `8a4e50e855ae646ca01df5524a51f5c494ac8ae13f3dea04834db4286247a7fa`.

## Backend evidence

| Backend | Artifact ID | ZIP bytes | Archive SHA-256 | Library | Native query mode |
|---|---:|---:|---|---|---|
| NetworkX | 15016032963 | 2,767 | `c770948fc43f51d7ac2464c3fab59d3bf3ec83fdc572e5cf388e0acc2b73591c` | 3.6.1 | `networkx_successor_predecessor_adjacency` |
| SciPy | 15015678205 | 2,925 | `80abd1a9e3b127c152b63ef227370626ce3cc3c041b45cd92830cb0ca36d8e9b` | 1.17.1 | `scipy_csr_csc_adjacency` |
| python-igraph | 15015618772 | 2,745 | `eb51d11e55594a4a74390ade097fa283d03327c467d6d03dc2af4c25c67a72a2` | 1.0.0 | `igraph_incident_edge_ids` |
| graph-tool | 15014954808 | 2,842 | `51e66d5bbfb51c326d387f17c0def447400661dd9138b602530ec5f83a4a1741` | 3.9 | `graph_tool_vertex_edge_iterators` |
| SNAP | 15016037991 | 3,428 | `fedf737956fd2c328fd8b11434561d14b90ac8aafd23e0a40e70a011586d3367` | 6.0.0 | `snap_isolated_worker_tneanet_edge_ids` |

Each backend passed seven E.8.5 cases and 14/14 parity-verified queries, with 34 native adjacency lookups and 96 native edge occurrences read. Each E.8.8 report passed 43/43 parity-verified queries, with 45 native adjacency lookups and 86 native edge occurrences read. Query failures and parity failures were zero in both reports.

The common E.8.8 repository snapshot was 26 nodes, 41 edge occurrences and 9 indexed files; graph fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`; source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. Context parity was 7/7 for trace execution, 16/16 for workflow context and 16/16 for nested workflow context. The two graph-to-source reads (`main.py` and `tests/checks.py`) matched their recorded SHA-256 hashes.

SNAP used worker image `sha256:4367b17c45d9d53c2a0337f44cda93755883e2e88e0972d94c500b4816880555`, Python 3.9.25 and SNAP 6.0.0. E.8.5 enforced a 120-second request timeout; E.8.8 enforced 30 seconds. The E.8.8 report verified network disabled, read-only root filesystem, no writable mounts, all capabilities dropped, no repository mount, no provider credentials, 512 MiB memory, one CPU and 64-PID limit. SciPy remains correctly described as a hybrid CSR/CSC topology representation plus exact semantic side channels.

## G4 Windows race result carried by this source

The same source includes the Windows handle-bound containment change in `evidence_tools.py`. [G4 run 45602554567](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554567) passed both the source-snapshot cost job and the Windows compatibility job. The Windows job passed 28 tests with 46 expected skips, including the deterministic test that replaces an in-root directory with an outside junction after component inspection and verifies that the opened handle's final path is rejected.

The handle-bound check uses `CreateFileW`, `FILE_FLAG_OPEN_REPARSE_POINT`, `GetFileInformationByHandleEx(FileAttributeTagInfo)` and `GetFinalPathNameByHandleW`; it compares the actual opened file path against the held root-handle path and reads from that same file handle. This closes the tested junction-replacement-to-outside schedule. It does not establish atomic repository-wide snapshot semantics or cover every Windows namespace/reparse-point type.

## G7 conclusion

**G7 — Evidence integrity: Pass for the exact five-backend E.8.5/E.8.8 artifact set from run 45602554671.**

The detached verifier matched all five original ZIPs to the pinned artifact IDs, sizes and archive digests, then validated report provenance and declared semantic contracts. This is detached archive-byte/digest and report-consistency verification. It does **not** rerun the historical workflows, independently reproduce the physical runner environments, or provide signed runner attestation. Hashes are integrity identifiers, not cryptographic signatures.

G4 is improved by the Windows handle-bound containment check but remains **Partial**: repository-wide atomic snapshot semantics, all external filesystem side effects, hard-link aliasing, arbitrary mutation/restoration schedules and native-projection postflight-to-return concurrency remain unresolved.

All 20 task/backend suitability outcomes remain **Insufficient evidence**. No global ranking, performance winner, automatic selector, scientific approval, runtime promotion or production approval is inferred. `production_approval=false` remains invariant.

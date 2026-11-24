# AE-32C M7.4 — Detached E.8.5/E.8.8 Evidence Dossier

**Status:** Verified
**Workflow:** [Run 45395352748](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45395352748), attempt 1
**Tested source:** `stage1/section-uuids` at `51d025fd328b00a59988a05fe72d9092262434f5`

## Method and scope

Downloaded the five Actions artifact ZIPs by exact artifact ID; recomputed the ZIP sizes and SHA-256 values and matched the GitHub Actions artifact metadata. The standalone verifier required the expected two JSON reports per ZIP and checked archive-member safety, report schema, source/run/attempt provenance, backend/library/native mode, E.8.5 and E.8.8 query/parity counts, native telemetry, projection round-trip, repository snapshot, context-operation telemetry, source-file hashes, side-effect boundaries and SNAP worker restrictions.

Verifier implementation: `tools/gb08_m74_native_conformance_dossier.py`, SHA-256 `94f1b42f81fed87123aed8b77e1d0560609a9bfe895502c05afde2b00fa7179f`. Unit tests: `tests/semantic_graph/test_m74_detached_native_conformance_dossier.py`, SHA-256 `1b2fd632ebcaf46e0f7f4607ea5b367f636093f929116f309242f47491a14666`. Executed under Python 3.13.5; all 11 adversarial tests passed.

## Backend evidence

| Backend | Artifact ID | Bytes | Archive SHA-256 | Library | Native path |
|---|---:|---:|---|---|---|
| NetworkX | 14920662487 | 2768 | `daf49717450bc776001b4a86e690329412b184a39afbbfd3186260ee2b9dc6aa` | 3.6.1 | `networkx_successor_predecessor_adjacency` |
| SciPy | 14920921665 | 2928 | `11491e4a4b16f0c8a5ca060a9882c6fdd97fd60c365c3831a8c410c6ae86b8e5` | 1.17.1 | `scipy_csr_csc_adjacency` |
| python-igraph | 14921070985 | 2747 | `43dfe79abd2e9d0931b2417d82dd7c45bbfe5b510b99e14d44fed3c615877c7a` | 1.0.0 | `igraph_incident_edge_ids` |
| graph-tool | 14920508045 | 2845 | `6ae437eefa6be0d15956855b7b8c271393c4c68cc15bcb9717e008e11eadddd` | 3.9 | `graph_tool_vertex_edge_iterators` |
| SNAP | 14920592009 | 3431 | `e5ff53b2ee4d86c7534d080bf96558618445a8d7d4281e6f854a3c0bd45eac30` | 6.0.0 | `snap_isolated_worker_tneanet_edge_ids` |

Each artifact was nonexpired and GitHub metadata bound it to run 45395352748, attempt 1, branch `stage1/section-uuids`, source `51d025fd328b00a59988a05fe72d9092262434f5`. Every E.8.5 report passed seven conformance cases and 14/14 parity-verified queries, with 34 native adjacency lookups and 96 edge occurrences read; every E.8.8 report passed 43/43 parity-verified queries, with 45 native adjacency lookups and 86 edge occurrences read. No query or parity failures were reported.

The common E.8.8 repository snapshot is 26 nodes, 41 edge occurrences and 9 indexed files, fingerprint `graph:1aca2caea6acabcf695a6118f7202b6e`, source-manifest SHA-256 `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`. Context parity: trace execution 7/7; workflow context 16/16; nested workflow context 16/16. The two source reads (`main.py` and `tests/checks.py`) matched their recorded SHA-256 hashes.

SNAP's isolated worker was image `sha256:a3ab78cf8512048adfc3570bff591772c1542dfb09226363142c6779934f59a5`, SNAP 6.0.0 / worker Python 3.9.25; the E.8.8 report confirmed network-disabled, read-only-root, no-writable-mount, no-capability, no-repository-mount, no-credentials, 512 MiB, one-CPU, 64-PID policy and a 30-second request deadline. SciPy's CSR/CSC representation remains correctly classified as hybrid: topology in sparse matrices, semantic edge occurrences and attributes in exact side channels.

## G7 closure

**G7 — Evidence integrity: Pass for this exact five-backend E.8.5/E.8.8 evidence set.** Manifest: `evidence/m74-e85-e88-run-45395352748/manifest.json`, SHA-256 `ff13bff4d7b2f57e425e2566b90797cbd22016ec048926e9ea590f67e79444d3`. Verified dossier: `evidence/m74-e85-e88-run-45395352748/verified-dossier.json`, SHA-256 `43137fb5a2ad24bb3afbd522b2b6445959501560abc001845b6051141710437a`.

Limitations: this is detached archive-byte/digest and report-consistency verification. It does not rerun the historic workflow, independently reproduce the build, or provide physical-runner attestation. G9.42 run 45400741779 is a separate validation bundle.

G7 closure does not close G2/G4/G5/G6 or domain-specific task fit. Stale/corrupt projection and mutation-race coverage, representative audit-domain workloads, broader operational/resource envelopes, PATH claim-to-evidence follow-through and the hybrid IMPACT canonical-graph SCC boundary remain unresolved. All 20 task/backend outcomes remain **Insufficient evidence**; there is no ranking, selection or promotion. `production_approval=false` remains invariant.

## Reproduction

Unzip the five original Actions ZIPs into an artifact directory as `networkx.zip`, `scipy.zip`, `igraph.zip`, `graph_tool.zip`, `snap.zip`, then run:

```bash
python tools/gb08_m74_native_conformance_dossier.py --artifact-dir /path/to/artifact-zips --manifest docs/audit-engine/evidence/m74-e85-e88-run-45395352748/manifest.json --output /path/to/verified-dossier.json
python -m unittest discover -s tests/semantic_graph -p 'test_m74_detached_native_conformance_dossier.py' -v
```

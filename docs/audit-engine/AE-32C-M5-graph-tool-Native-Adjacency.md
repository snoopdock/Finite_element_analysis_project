# AE-32C M5 — graph-tool Native Adjacency Implementation Record

**Status:** Accepted for the tested graph-tool-base 3.9 / CPython 3.11.18 repository path; production approval remains false  
**Milestone:** M5 — graph-tool native adjacency  
**Target branch:** `stage1/section-uuids` only  
**Predecessor:** M4 accepted by G9.42 run [44901309538](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44901309538), exact Stage1 SHA `c6d4fda93897a3b7022d28cba177fc5c453940b3`  
**Scope:** graph-tool native local edge traversal. SNAP remains unimplemented.

## 1. Objective and authority boundary

Replace the generic full-native-graph-to-Python-adjacency fallback for graph-tool with native per-vertex incoming/outgoing edge iteration. Preserve `SemanticGraph` as the sole authority for semantic node IDs, occurrence IDs, evidence, payloads and traversal semantics. Native vertex and edge descriptors are projection-local references, not persistent semantic identities.

This milestone does not change graph-tool serialization claims, promote graph-tool to production-approved, or claim a performance advantage. Object-valued property maps remain in-memory only.

## 2. API selection and rationale

The implementation uses the graph-tool directed multigraph interface:

- `Graph.vertex(index)` resolves the projection-local vertex descriptor.
- `Vertex.out_edges()` enumerates only outgoing edge descriptors for that vertex.
- `Vertex.in_edges()` enumerates only incoming edge descriptors.
- Each edge descriptor exposes `source()` and `target()`.
- `Graph.edge_index[edge]` supplies the native edge index; the adapter maps this explicitly to the canonical semantic occurrence.
- Edge and vertex property maps retain relation labels, attributes, metadata and semantic identities.

The official graph-tool quick-start documents directed per-vertex `out_edges()`/`in_edges()` iteration, edge descriptor endpoints and the `edge_index` property map. It also cautions that edge indices need not remain contiguous after removals, so the implementation does not assume edge index equals the occurrence ID or list position. [Quick-start guide](https://graph-tool.skewed.de/static/docs/stable/quickstart.html)

graph-tool's `Graph` is documented as a general multigraph. This is important: the implementation retains distinct parallel edge occurrences rather than collapsing them to a single endpoint pair. [Graph API](https://graph-tool.skewed.de/static/docs/stable/autosummary/graph_tool.Graph.html)

## 3. Implementation

### 3.1 Projection and explicit native-edge mapping

`GraphToolAdapter` continues to build a directed `graph_tool.Graph` with property maps for:
- semantic node ID and entity type;
- node attributes and metadata;
- edge relation;
- edge attributes and metadata;
- canonical semantic edge occurrence ID.

During construction, each returned native edge descriptor is resolved through `native.edge_index`; the adapter builds `native_edge_id_to_occurrence`. This avoids relying on endpoint pairs, edge iteration order, or an assumption that graph-tool edge indices are contiguous. Duplicate native edge indices are rejected.

The native graph receives deep-copied property values. The canonical graph and its semantic occurrence mapping remain authoritative.

### 3.2 Native local adjacency

`GraphToolAdapter.iter_adjacent_edge_occurrences(node_id, direction)`:
1. Resolves the semantic node ID to its projection-local vertex index.
2. Calls only `vertex.out_edges()` for outgoing traversal.
3. Calls only `vertex.in_edges()` for incoming traversal.
4. For `BOTH`, unions the selected native edge descriptors by canonical occurrence ID. A self-loop present in both iterators is therefore emitted once.
5. Resolves each descriptor's native edge index to the canonical occurrence ID.
6. Checks the occurrence property, endpoints, relation, attributes and metadata against the immutable projection snapshot.
7. Returns typed `NativeEdgeOccurrence` records sorted by semantic occurrence ID for deterministic downstream behavior.

Parallel edges remain separate because they have distinct graph-tool edge indices and distinct canonical occurrence IDs. No endpoint-only lookup such as `Graph.edge(source, target)` is used; such an API can return one edge or a list, but the explicit per-edge descriptor/property mapping is the safer identity contract for this adapter.

### 3.3 Construction audit, traversal and telemetry

The shared native traversal engine validates the complete graph-tool projection once during construction. After this succeeds, it retains cached projection counts and supplies empty Python adjacency dictionaries to subsequent walks. Candidate edges are obtained through the graph-tool adapter's native local iterators.

The deterministic reference traversal continues to own BFS ordering, depth/step/visited-node limits, relation filters, evidence construction and per-query parity verification. Runtime reporting does not enumerate the full graph. The native query mode is `graph_tool_vertex_edge_iterators`.

The adapter reports:
- native adjacency lookups;
- outgoing edge-iterator lookups;
- incoming edge-iterator lookups;
- native edge occurrences read.

The registry state is `implemented_unvalidated`; `production_approval` remains false.

### 3.4 Property-map and serialization boundary

The adapter uses graph-tool `string`, `int64_t` and `object` property maps. graph-tool documents `object` as the `python::object` property-map value type. These maps are appropriate for in-process Python payloads, but this implementation does not claim that arbitrary Python objects are portable through graph-tool binary/XML serialization. The existing loss report continues to state the in-memory-only boundary. [graph-tool quick-start — property maps](https://graph-tool.skewed.de/static/docs/stable/quickstart.html)

## 4. Tests and conformance gates added

The E.8.3 test module now covers:

- fake graph-tool vertex descriptors with `out_edges()` and `in_edges()`;
- explicit native edge-index to semantic-occurrence mapping, including non-contiguous native indices in the fake API contract;
- outgoing and incoming local adjacency;
- two parallel A→B occurrences with distinct relations;
- incoming B→C and a C→C self-loop in `BOTH`, with the loop returned once;
- deterministic occurrence ordering and parity with the Python reference;
- mutation detection for native edge payloads;
- runtime native adjacency counters;
- a guard that forbids full native node/edge enumeration during queries and runtime reporting;
- repository-backed context-tool routing, native telemetry, parity and source follow-through when graph-tool is installed;
- E.8.5 synthetic conformance in the graph-tool fake-module contract.

The real-library test remains conditional. Fake-module tests verify the consumed API contract but do not establish graph-tool binary compatibility.

## 5. Validation environment

The normal G9.42 dispatcher installs `requirements.txt` under CPython 3.11 and does not install graph-tool. The prior M4 artifact explicitly recorded graph-tool as unavailable in that interpreter. graph-tool is not a suitable default pip dependency for this project.

A dedicated conda-forge environment already exists at `.github/environments/e85-graph-tool.yml`. The manual E.8.5/E.8.8 workflow has been updated so its graph-tool job:
1. provisions that Python 3.11 environment with `mamba-org/setup-micromamba`;
2. runs graph-tool adapter tests from `test_e83_multi_backend_traversal.py`;
3. runs the synthetic E.8.5 native projection/traversal conformance tool;
4. runs the E.8.8 repository-backed context/source conformance tool;
5. uploads both synthetic and repository reports.

Workflow: [E.8.5 / E.8.8 Native Graph Backend Conformance](../../.github/workflows/e85-native-graph-backend-conformance.yml).

The M5 acceptance record must bind both:
- a passing G9.42 report for the exact Stage1 source SHA (full targeted and regression suites, evidence integrity, immutable bundle and provenance catalog); and
- a passing graph-tool-specific workflow artifact from the same exact Stage1 source SHA, showing the real graph-tool version, real adapter tests, synthetic conformance and repository-backed conformance.

A G9.42 run where graph-tool tests are skipped is necessary for broad regression but is not sufficient for real graph-tool acceptance. A green E.8.5/E.8.8 job alone is also insufficient without the exact-commit G9.42 regression/evidence chain.

## 6. Acceptance boundary

The required exact-source validation has now passed for Stage1 SHA `9adc99b9511d0281b18be76d60865dcf13bb16b0`: G9.42 run `44904263386` and dedicated E.8.5/E.8.8 run `44905580330` both tested that exact SHA. The graph-tool job installed graph-tool-base 3.9 under CPython 3.11.18, ran four real adapter tests, and produced passing synthetic and repository-backed reports with positive native-adjacency telemetry. See Section 9 and the run failure review for the SNAP-only workflow failure.

Do not interpret this milestone acceptance as production approval or a performance claim. The runtime registry intentionally remains `production_approval=false`.

The acceptance gates were:

1. Real graph-tool tests execute in the supported conda-forge environment rather than skip.
2. The adapter preserves every node and edge occurrence, including parallel edges and self-loops.
3. Outgoing, incoming and `BOTH` results match the canonical reference exactly.
4. Native query and occurrence-read counters are positive; full node/edge enumeration is absent during query and report.
5. Native projection mutation fails closed.
6. Repository conformance verifies `graph_tool_vertex_edge_iterators` for all three context operations, with positive native lookup/occurrence telemetry, zero parity failures and verified source follow-through.
7. The complete G9.42 targeted and regression suites pass on the same exact source SHA, and evidence integrity, bundle publication and provenance verification pass.

**Disposition:** M5 is accepted for the tested graph-tool-base 3.9 / CPython 3.11.18 environment and repository context path. The capability registry's `implemented_unvalidated` state and `production_approval=false` are intentionally retained until a separate runtime approval decision. M6 SNAP work remains deferred pending its isolated compatibility probe and later worker/adapter implementation.

## 7. Implementation commits

- `b91f439a79fff9b8c4b09aa6e0a16e0abf8b5dee` — add graph-tool native local edge adjacency and native edge-index/occurrence mapping.
- `7d638b55163c3113c0727dd0308680c258cc7e42` — route graph-tool traversal through native edge iterators and cached projection counts.
- `97c05098b462ab5ec9c9b95f0a3665deab813e93` — mark graph-tool native adjacency implemented but unvalidated.
- `d4a94d8d74ce01677cd49f6f98036c055869be48` — add fake graph-tool adjacency contract coverage.
- `7cc826cc27b144169a002be8fcb4642f0895433b` — use graph-tool vertex descriptor indices for edge identity.
- `3f5577a8ffc0b288565890ea13fd6acb645afaa9` — model graph-tool vertex descriptors in the test double.
- `b6b59b2124d29e8171b77628e2eb00d783510cf0` — add graph-tool mutation and repository conformance tests.
- `d77bd4055234d2f2230fea9679960fa71df11315` — run graph-tool repository conformance in the dedicated native workflow.
- `25161900a8197a98db06734865d793ad1a5d8427` — update native workflow acceptance summary.
- `cdcf91ee60d148652e2c054d286224019344ce63` — execute graph-tool adapter tests in the dedicated conformance environment.
- `8f308d75e2cf2fd32d4c813988cec1eef98280ed` — align the GB-01 architecture note with the M5 implementation.
- `9768be5813ec5fa003820ff0291424c710ed0205` — clarify M5 remaining validation and acceptance gates.
- `280dfccb427824e71dca61c90bc7e19f1a03219e` and `137b74bcb5f2908c8379e3ec72584a260492cd7e` — report the installed `graph-tool-base` distribution version consistently in runtime and synthetic conformance evidence.
- `80f72b680b5f9b5e9bb15c1cf739cdd7d39cccd1` — update the legacy graph-tool projection fake to expose the edge-index property map consumed by the adapter.
- `7becea4463b9276cbcdd49ad83f12a65d82806b7` — update the registry contract test to distinguish graph-tool's `implemented_unvalidated` state from SNAP's `not_implemented` state.
- `beb4b80b00361aa882c00d97707090e2c0b651a6` — strengthen the graph-tool fake to exercise non-contiguous native edge indices and explicit occurrence mapping.
- `5d8c050450ff0a77cd88938d06d26e48ccfa08dc` — clarify the scope of the legacy graph-tool fake.
- `17be6d8069a5776f4974dadd0a006a847f56c74c` — record sparse-index contract coverage.
- `5ebd3d9771cd3a61c7d997f5b0c1bea62bdbc946` — document the G9.42 failure review, evidence chain and correction rationale.

No local tests or workflows were run by the implementer. M5 implementation remains subject to user-run G9.42 and graph-tool-native workflow validation.


## 8. G9.42 validation attempt and correction

G9.42 run [44902653878](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44902653878) checked out Stage1 source SHA `e979b17b081d5e0a3cf120b184c7016de6dfd3e1`. The dispatcher itself was launched from `main`, but the workflow explicitly checked out `stage1/section-uuids`; the report and checkout log agree on the tested source SHA. No source changes were made to `main`.

The targeted suite passed (689 tests, 5 skipped). Full regression had 3 failures (3,628 total; 3,612 passed; 13 skipped):
- two legacy graph-tool fake tests lacked the `Graph.edge_index` property map now consumed by `GraphToolAdapter`;
- one M1 registry assertion still expected graph-tool to be `not_implemented` after M5 had registered it as `implemented_unvalidated`.

The detached evidence digest check passed and the immutable evidence bundle was published and verified. Provenance catalog build and verification correctly failed closed because the validation report had a failed test outcome. Artifact SHA-256: `f10d5dcf2091311418dc74a29499486c33440e6d94d721d681daa465956e363e`; report SHA-256: `d5d7b7c86d6bd7238ce438acd3d9b50a9983ef1df703524d76a2e85e6c34bb75`; bundle SHA-256: `5e0546da43d5b0c5b8ce7e37d80b90b5c0292400939c8d2f05e7250c3693eb51`.

The two test-contract defects were corrected in commits `80f72b680b5f9b5e9bb15c1cf739cdd7d39cccd1` and `7becea4463b9276cbcdd49ad83f12a65d82806b7`. See [M5 G9.42 Validation Failure Review — run 44902653878](AE-32C-M5-G9.42-Validation-Failure-44902653878.md) for the failure traces and technical rationale.

**Disposition:** corrections are committed but not yet validated. M5 remains `implemented_unvalidated`; production approval remains false. The next G9.42 run must test the latest Stage1 head. M5 acceptance still additionally requires the dedicated real graph-tool E.8.5/E.8.8 workflow to pass on the same exact source SHA.


## 9. Exact-commit validation — G9.42 and dedicated native workflow

Both acceptance workflows tested Stage1 source SHA `9adc99b9511d0281b18be76d60865dcf13bb16b0`.

### 9.1 G9.42 regression and evidence

Run [44904263386](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44904263386) passed:
- validation engine: 53 passed;
- targeted suite: 684 passed, 5 skipped, 0 failures/errors;
- regression suite: 3,615 passed, 13 skipped, 0 failures/errors;
- evidence integrity passed;
- immutable evidence bundle published and verified;
- provenance catalog built and verified.

### 9.2 Real graph-tool environment and conformance

Run [44905580330](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44905580330) installed `graph-tool-base 3.9` from conda-forge under CPython 3.11.18. The real graph-tool adapter/API tests reported **4 passed, 20 deselected**.

Synthetic E.8.5 report:
- `status=passed`;
- 34 native adjacency lookups;
- 96 native edge occurrences read;
- all seven fixture conformance cases passed;
- projection round-trip exact, including three parallel occurrences and one self-loop.

Repository-backed E.8.8 report:
- `status=passed`;
- 45 native adjacency lookups and 86 native edge occurrences read;
- zero query/parity failures;
- `trace_execution_context`, `find_workflow_context` and nested workflow-context execution reported `graph_tool_vertex_edge_iterators`;
- positive native lookup/occurrence-read telemetry and source follow-through verified.

The overall workflow was marked failed solely because the separate SNAP Python 3.9 setup step requested CPython 3.9.19 on Ubuntu 26.04. SNAP installation and smoke steps were skipped. This does not invalidate the graph-tool reports or the matching G9.42 evidence.

**M5 acceptance:** satisfied for the tested graph-tool-base 3.9 / CPython 3.11.18 environment and repository context path. No performance superiority is inferred. The runtime registry remains unapproved for production.

## 10. SNAP compatibility workflow correction

The SNAP failure review is recorded in [AE-32C E.8.5/E.8.8 Run 44905580330 — Failure Review and Corrective Action](AE-32C-E85-Validation-Failure-44905580330.md).

The isolated SNAP job is now pinned to `ubuntu-24.04`, requests the CPython `3.9` minor line, and installs only the pinned `snap-stanford==6.0.0` binary wheel from `.github/environments/e85-snap-python39-requirements.txt`. It records setup/install/smoke outcomes for diagnostic artifacts. This change corrects runner provisioning; it does not assert that the smoke has passed. SNAP adapter implementation and repository acceptance remain future work.

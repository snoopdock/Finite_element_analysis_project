# AE-32C M7.4-G4 — Cross-Backend Snapshot and Mutation Integrity

**Status:** focused five-backend G4 test tranche passed; overall G4 remains Partial because off-neighborhood native mutation, repository-file non-mutation and broader concurrency/lifecycle coverage remain open.  
**Branch baseline:** `stage1/section-uuids` at `b536e35e35a83e7086efe69130e6c0d99ecb1d3b`.  
**Scope:** canonical graph snapshot isolation, mutation detection, local projection corruption, parity fail-closed behavior, repeated queries, reconstruction and SNAP worker teardown.

## 1. Acceptance boundary

G4 is evaluated against the invariant that `SemanticGraph` remains the canonical semantic authority. A backend projection is a computational snapshot; it does not become an alternate semantic source. For this tranche, a passing test means that a bounded query does not mutate canonical graph data, that nested payloads copied into a projection do not alias later caller mutation, that canonical mutation is detected around a query, and that corrupt or incomplete local native adjacency cannot be silently accepted.

This tranche does **not** close G4. The tests use controlled in-memory graphs and injected failure modes. Repository-file side effects, arbitrary concurrent mutation schedules, and off-neighborhood native-object corruption are not fully qualified here.

## 2. Source inspection before test design

The implementation inspected at the branch baseline included:

- `optional_backend_support.make_projection`: validates node identity, edge endpoint membership and mapping payload types, and deep-copies node/edge attributes and metadata before native projection construction.
- `NetworkXGraphTraversalEngine`: clones its input projection, validates the complete NetworkX node/edge projection during initialization, then reads native local adjacency and checks each returned occurrence against canonical edge identity and payload. It compares canonical graph fingerprints before and after query execution.
- `NativeAdapterGraphTraversalEngine`: validates the complete non-NetworkX projection during initialization, obtains query candidates from the selected native local-adjacency API, validates each returned occurrence, and checks the canonical graph fingerprint before and after traversal and parity verification.
- SciPy maintains CSR/CSC connectivity plus semantic edge-occurrence side channels; igraph and graph-tool retain native edge-occurrence identifiers; SNAP runs behind the isolated worker protocol and maps worker edge IDs back to snapshot occurrence IDs.

The code already contains material G4 controls. The missing evidence was a focused five-backend test matrix covering mutable nested payloads, query-time canonical mutation, corrupted local records, missing local records, repeated execution and reconstruction.

## 3. Added test cases

New module: `tests/semantic_graph/test_m74_snapshot_mutation_integrity.py`.

Each case is parameterized across NetworkX, SciPy, python-igraph, graph-tool and the isolated SNAP worker, with workflow-level backend selection preventing a generic interpreter from misreporting unavailable native libraries as executed tests.

| Test case | Required observation |
|---|---|
| Deep snapshot isolation | Mutating nested canonical node/edge payloads after adapter construction does not rewrite the already-created backend snapshot; a subsequent query against the stale canonical snapshot fails closed. |
| Mutation during native adjacency | A mutation to an unreached canonical node after native adjacency has been read is detected by the graph-wide fingerprint guard before a result is accepted. |
| Corrupted local occurrence | A local edge record whose metadata no longer matches the canonical edge occurrence is rejected. |
| Missing local occurrence | With reference parity enabled, a native adjacency response that omits expected occurrences is rejected rather than returned as a successful traversal. |
| Repeated query and reconstruction | Repeated results are identical; a fresh projection over the unchanged canonical graph reproduces the result; SNAP refuses a query after worker closure instead of falling back silently. |

The fixture intentionally includes nested mutable dictionaries/lists, parallel edge occurrences and a self-loop. It avoids relying on any backend's private index representation.

## 4. Workflow integration

The E.8.5/E.8.8 workflow now runs the dedicated G4 module in each backend environment:
- NetworkX, SciPy and igraph matrix jobs, selected by `AE32C_M74_BACKEND`;
- the dedicated graph-tool environment;
- the isolated SNAP worker job after immutable worker-image identity has been recorded.

The workflow is configured for `workflow_dispatch` and for pushes to `stage1/section-uuids` that touch `tests/semantic_graph/**` or the workflow itself. Therefore, committing the test and workflow changes should initiate the native backend matrix automatically. The source SHA in the resulting run must be recorded and checked; the workflow being triggered is not itself a pass.

## 5. Known residual limits — do not overstate G4

1. **Repository-file non-mutation:** this test module operates on synthetic in-memory graphs. It does not open or write repository files. The existing E.8.8 repository fixture has its own source-read and no-side-effect checks, but that evidence does not by itself establish every repository operation's mutation boundary.
2. **Concurrent schedules:** the tests inject a deterministic mutation during a native adjacency call and verify the post-query fingerprint guard. They do not exhaust thread interleavings, mutation-and-restoration between fingerprint checks, or all lifecycle races.
3. **Mutable exported native objects:** adapter exports expose backend-native objects. The current engines perform full projection validation at construction and validate the local adjacency records used by a query; they do not re-enumerate the entire native graph before every bounded query. Consequently, corruption confined to a disconnected or unvisited native region may not be detected by a query that never touches that region. A future policy must decide whether to restrict mutable export access, provide defensive views/copies, or explicitly pay for full projection revalidation. Do not claim global immutability or universal detection of off-path native mutation from this tranche.
4. **SNAP lifecycle:** the tests verify fail-closed behavior after worker closure and successful reconstruction through a new adapter. They do not replace the dedicated live Docker timeout/termination and container-removal suite.

## 6. Evidence and decision status

At the implementation commit, execution was pending. The exact-source run has now completed successfully; its verified record follows in Section 7. The run is interpreted within the residual scope below:
- exact Stage1 source SHA and attempt;
- all five G4 backend jobs executing the new module (not skipped);
- per-backend test totals, failures and skips;
- full E.8.5/E.8.8 jobs and aggregate summary, because G4 is inserted into that existing matrix.

G4 remains **Partial / insufficient evidence** until the five partitions complete and the remaining residual limits are addressed or explicitly bounded by the contract. All 20 task/backend suitability outcomes remain `Insufficient evidence`. No backend ranking or automatic selection follows. `production_approval=false` remains invariant.


## 7. Exact-source G4 matrix execution — 2026-11-24

**Workflow:** [45413494767](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45413494767), attempt 1, push-triggered, completed with conclusion `success`.  
**Tested source:** `stage1/section-uuids` at `7447a6b6327b2f310012088767df8251577f6cb1`. Every backend job logged this same `AE32C_SOURCE_REVISION`.

| Backend | Job ID | G4 pytest result |
|---|---:|---:|
| NetworkX | 138513333211 | 5 passed, 20 skipped |
| SciPy | 138513333115 | 5 passed, 20 skipped |
| python-igraph | 138513333610 | 5 passed, 20 skipped |
| graph-tool | 138513333134 | 5 passed, 20 skipped |
| SNAP isolated worker | 138513332413 | 5 passed, 20 skipped |

The 20 skips in each job are the other four backend partitions excluded by `AE32C_M74_BACKEND`; the selected backend's five parameterized G4 cases executed in each environment. Across the five selected environments, all 25 intended backend-specific test executions passed, with no G4 test failure or error. The SNAP job supplied worker image ID `sha256:033de68b84778a7f67de0492e9fe558ff4bed3fbc26b5235a249875ddd88ccd8`; its post-close query assertion passed as part of the SNAP G4 tests.

All five E.8.5/E.8.8 backend jobs and aggregate summary job `138514348900` also concluded `success`. The run's E.8.5 and E.8.8 reports both recorded `status=passed` for each backend, with E.8.5 14/14 and E.8.8 43/43 parity-verified queries and zero query/parity failures. The five uploaded evidence artifacts are:

| Artifact | ID | ZIP size | Actions SHA-256 |
|---|---:|---:|---|
| NetworkX | 14931650153 | 2,769 bytes | `c46c44ed9f8b9e5cb045e37973829d98440f3eb3ad1e2e41549da0181bc72a35` |
| SciPy | 14931365165 | 2,928 bytes | `12c37b9562a9f2d2298562f30e492b53f9f5ca9a1aa0ad86d7e171ae37201c51` |
| igraph | 14930975424 | 2,746 bytes | `151ba1888095f028fa505f2e9dde7b135b1a7447edca97734c76da9c6fc08585` |
| graph-tool | 14929461149 | 2,845 bytes | `e5184c365174a7ca7120382eaf143c62b57cc65b878ffa33b140bea8e0f4f251` |
| SNAP worker | 14932195241 | 3,428 bytes | `413ec55b6f8c9b6ed8f3253086a8190ef4dd24682201029b7658bfed97a1af83` |

These artifact digests are the GitHub Actions-reported ZIP digests. They do not represent a detached G7 verification of this new run's E.8.5/E.8.8 artifacts; the earlier G7 dossier remains bound to run 45395352748 and its exact historical source.

**G4 interpretation:** the new focused five-backend test tranche passes. This does not close G4. The suite establishes the tested snapshot/query behaviors, but it does not establish global immutability or detection of arbitrary off-neighborhood corruption in mutable native exports. Repository-file no-side-effect behavior and broader concurrency/lifecycle limits also remain. Maintain G4 as Partial and leave all 20 task/backend suitability outcomes at Insufficient evidence. `production_approval=false` remains invariant.

## 8. G4 continuation — complete projection preflight/postflight (implementation pending execution)

The next implementation tranche changes the query integrity boundary for all five backends:

- **Before traversal:** re-enumerate the complete native node and edge-occurrence projection and compare it with the canonical `SemanticGraph`.
- **After traversal and reference-parity work:** repeat the complete projection audit before accepting the result.
- **NetworkX:** rerun full node/edge/occurrence verification at each boundary, including context-adjacency operations.
- **SciPy, igraph and graph-tool:** remove the construction-only validation shortcut. Each query re-enumerates native nodes and all native edge occurrences, while the actual traversal continues to use CSR/CSC, incident-edge IDs or graph-tool edge iterators.
- **SNAP:** add an explicit fresh worker-audit operation so a query does not rely on the adapter's prior audit cache; the complete audit is requested at both boundaries.

The test module now adds:
1. direct off-neighborhood native-projection corruption before a bounded query (NetworkX, SciPy, igraph and graph-tool); SNAP uses a deliberately corrupted fresh audit response because its worker graph is intentionally not exported into the host;
2. off-neighborhood mutation after local adjacency but before query completion, checked by postflight;
3. a SNAP-specific assertion that exactly two fresh `audit` RPCs bracket one query.

These checks target the former blind spot: a query rooted at A must reject a corrupted C-to-C self-loop even though C is outside A's one-hop result.

**Cost and limits:** complete validation adds O(V+E) work before and after each bounded traversal. SNAP additionally incurs two full audit RPCs per query. This is a deliberate integrity/performance tradeoff, not a free strengthening; subsequent task-workload and operational evidence must quantify it. The checks do not establish immutability, prevent an attacker or concurrent writer from mutating and restoring state entirely between observations, or close a race after the final postflight. Repository-file side-effect coverage remains separate.

**Status at this record:** implementation and tests prepared; exact-source five-backend execution pending. G4 remains Partial until the new matrix passes and remaining concurrency/repository-side-effect limits are either tested or explicitly bounded in the contract. All 20 task/backend outcomes remain Insufficient evidence; `production_approval=false`.

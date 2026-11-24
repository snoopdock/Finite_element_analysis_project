# AE-32C M7.4-G4 — Cross-Backend Snapshot and Mutation Integrity

**Status:** G4 test tranche added; five-backend runtime evidence pending.  
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

At commit preparation time, the tests and workflow integration have been added but **have not yet been executed by GitHub Actions**. The resulting run must be inspected for:
- exact Stage1 source SHA and attempt;
- all five G4 backend jobs executing the new module (not skipped);
- per-backend test totals, failures and skips;
- full E.8.5/E.8.8 jobs and aggregate summary, because G4 is inserted into that existing matrix.

G4 remains **Partial / insufficient evidence** until the five partitions complete and the remaining residual limits are addressed or explicitly bounded by the contract. All 20 task/backend suitability outcomes remain `Insufficient evidence`. No backend ranking or automatic selection follows. `production_approval=false` remains invariant.

# AE-32C M7.4 — SNAP bounded streaming transport design

**Status:** Design decision for the next implementation tranche; not implemented or accepted.  
**Branch:** `stage1/section-uuids`  
**Baseline source:** `e8c8b45ef345fca1da25f34bb468d111f03f8417`  
**Observed blocker:** M7.4 run [45778108441](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45778108441) skipped the full-repository SNAP campaign because the single JSON-lines initialization request exceeded the 16 MiB limit.

## 1. Problem statement

The present protocol sends the complete graph in one `init` request. Both host and worker enforce a 16 MiB line limit. The limit is an intentional safety boundary, not a reason to increase the maximum line size. The M7.4 full-repository campaign therefore did not construct a SNAP graph and supplies no SNAP full-repository task result.

Simply raising the line cap is rejected. It would increase peak frame allocation, preserve a monolithic failure mode, and leave the worker's full-projection `audit` response subject to the same framing problem. A correct solution must stream both initialization and full native projection readback.

## 2. Protocol versioning and invariants

Introduce a new protocol identifier, `ae32c/snap-worker/v2`. Do not negotiate v1/v2 implicitly and do not retry a failed v2 stream as v1.

The following invariants are mandatory:

1. The canonical `SemanticGraph` and its host-side projection remain authoritative.
2. Every accepted node and edge occurrence is transferred exactly once.
3. Node identity, edge occurrence identity, endpoints, relation, attributes and metadata survive round-trip without lossy coercion beyond the already declared canonical-JSON representation.
4. The worker constructs TNEANet only after the complete initialization stream passes count, ordering and digest checks.
5. Full projection preflight/postflight remains mandatory at query boundaries; streaming must not weaken G4.
6. Any timeout, malformed frame, missing/duplicate/reordered chunk, count mismatch, digest mismatch, or resource-limit breach fails closed and tears down the worker.
7. No query may run against a partially initialized graph.
8. No automatic fallback to another backend is permitted.

## 3. Bounded frame and stream model

Keep each JSON-lines frame small and independently bounded. The initial implementation target is:

- maximum encoded protocol frame: 1 MiB;
- target chunk payload: at most 512 KiB before JSON envelope overhead;
- maximum node count: 200,000;
- maximum edge-occurrence count: 1,000,000;
- aggregate snapshot byte limit: **not yet selected**; determine it from measured serialized size, worker peak RSS, construction overhead and the 512 MiB container limit before enabling the full-repository campaign;
- independent wall-clock budget for the complete initialization stream, in addition to the existing per-RPC timeout.

The aggregate byte cap must not be inferred from the 16 MiB line cap. It must be selected from measured memory headroom under the exact SNAP 6.0 / CPython 3.9 worker image. Until that measurement exists, the implementation must retain a conservative configurable cap and report `snapshot_size_limit_exceeded` explicitly.

## 4. Initialization state machine

The host sends these operations:

| Operation | Required content | Worker behavior |
|---|---|---|
| `snapshot.begin` | protocol version, request ID, graph fingerprint, expected node/edge counts, declared node/edge chunk counts, aggregate byte count and declared stream digest | Validate limits; create an empty pending snapshot; reject if already initialized or another stream is open |
| `snapshot.nodes` | zero-based chunk index, records, chunk byte count, chunk SHA-256 | Require the next exact index; validate each node record; update stream digest and counters |
| `snapshot.edges` | zero-based chunk index, records, chunk byte count, chunk SHA-256 | Require the next exact index; validate endpoints against the declared node identity set; validate occurrence sequence and record shape |
| `snapshot.commit` | final node/edge counts, chunk counts and stream digest | Verify all declarations; only then construct TNEANet and publish initialized state |

Node and edge streams have independent chunk indexes and digest domains. Each chunk digest is SHA-256 over the exact canonical UTF-8 JSON bytes of the record array. The aggregate digest is SHA-256 over a domain-separated, length-prefixed sequence of (stream kind, chunk index, chunk byte count, chunk digest). The host and worker must implement the same documented byte encoding; no language-default JSON serialization is permitted.

The worker must reject:
- a chunk before `snapshot.begin`;
- a second begin while a stream is pending;
- an index other than the next expected index;
- a duplicate chunk;
- records beyond declared counts;
- a chunk or aggregate size above the configured limit;
- a commit with missing chunks or mismatched counts/digests;
- node or edge records with invalid identity, endpoint, type, relation or JSON payload.

A pending stream is discarded on any error or timeout. Native graph construction starts only after commit validation.

## 5. Streaming full-projection audits

Initialization streaming alone is insufficient. G4 requires complete native projection validation before and after a bounded query, and the current `audit` response returns all nodes and edges in one line.

Replace the monolithic audit response with a paged readback:

1. `audit.begin` returns a fresh audit ID, node/edge counts and the worker's graph fingerprint.
2. `audit.nodes` and `audit.edges` return bounded pages selected by audit ID, stream kind and zero-based offset/limit. Pages include exact record indexes and a per-page digest.
3. `audit.finish` returns the complete readback stream digests and counts.
4. The host rejects duplicate, missing, reordered, overlapping or out-of-range records; verifies page and aggregate digests; and compares every record against the host projection.
5. The audit ID is single-use. A new query boundary requires a new audit ID and fresh native readback.

Pages must be bounded by encoded response bytes, not only record count, because attribute and metadata sizes vary. The worker must not return a page larger than the configured frame limit. Host page retrieval must have a total audit deadline and must fail closed on partial readback.

The existing two full projection audits per query remain required. Streaming is a transport change, not permission to reduce the validation frequency or trust a stale audit cache.

## 6. Resource accounting and telemetry

Every SNAP run must record:

- protocol version;
- worker image ID, CPython and SNAP versions;
- declared and actual node/edge counts;
- serialized node bytes, edge bytes and total bytes;
- node and edge chunk counts, maximum frame size and maximum page size;
- initialization wall time;
- peak worker RSS (or a documented runner/container measurement method);
- graph construction wall time;
- audit page count, total bytes and audit wall time;
- query count, native adjacency operations and edge occurrences read;
- timeout/cleanup outcomes and worker exit status.

The existing limits (512 MiB memory, one CPU, 64 PIDs, no network, read-only root, no repository mount, no provider credentials) remain unchanged during initial protocol qualification. If the measured workload cannot fit, the result is a resource-envelope failure, not a reason to silently relax isolation.

## 7. Required test matrix

### Protocol unit tests

- valid multi-chunk graph with Unicode, nested JSON values, parallel edges and self-loops;
- exact chunk ordering and independent node/edge sequences;
- chunk reordering, duplication, omission and index gaps;
- altered chunk bytes, altered digest, altered aggregate digest;
- wrong declared counts and wrong total byte count;
- invalid node identity, duplicate node, invalid edge endpoint and duplicate occurrence;
- empty graph and zero-edge graph;
- a single record too large for one frame;
- exact frame-size boundary and one byte over;
- aggregate stream byte limit and count limit;
- interrupted stream followed by attempted query;
- worker rejects query before successful commit;
- worker rejects a second initialization;
- no fallback to protocol v1 or another backend.

### Audit paging tests

- exact multi-page readback of nodes and edges;
- empty and final partial pages;
- overlapping, duplicated, missing and reordered page indexes;
- altered page and aggregate digests;
- wrong audit ID and reuse of a completed audit ID;
- page response over frame limit;
- native projection mutation between pages;
- worker timeout during preflight and postflight;
- host detects a mismatch in a page outside the current query neighborhood.

### Live integration and M7.4 acceptance

- build the exact restricted SNAP image and record immutable image ID;
- execute E.8.5 and E.8.8 parity suites;
- execute G4 off-neighborhood preflight/postflight checks;
- execute the 1,897-file repository campaign on SNAP with the exact same source graph and query seeds used by the four in-process backends;
- verify identical semantic results against the reference engine;
- verify no repository writes, network calls or provider calls;
- capture worker RSS, frame/chunk metrics and complete initialization/audit timings;
- run a deliberately stalled mid-stream worker and verify exact container removal;
- independently verify all artifacts against run ID, attempt, source SHA, image ID and archive digests.

The SNAP result must be compared to the same declared task and graph inputs, not to a different workload. The objective is to establish whether SNAP can execute the relevant computation within a bounded, auditable resource envelope—not to rank libraries by speed.

## 8. Acceptance boundary

This protocol tranche is accepted only when:

- v2 framing and stream validation tests pass;
- initialization and full audits remain within measured limits;
- G4 integrity tests pass on the real worker;
- E.8.5/E.8.8 parity is exact;
- the full-repository campaign actually executes rather than skips;
- failure and cleanup tests demonstrate fail-closed behavior;
- detached artifact verification binds every result to the exact source and worker image.

Until then:
- SNAP full-repository task suitability = **Insufficient evidence**;
- G5 = **Partial**;
- the 16 MiB v1 line limit remains unchanged;
- no library ranking or automatic selection is authorized;
- `production_approval=false`.

## 9. Implementation sequence

1. Add v2 protocol schemas and pure canonical framing/digest helpers.
2. Implement worker initialization state machine and host streaming sender.
3. Implement worker paged audit and host completeness verifier.
4. Add adversarial protocol and audit-page tests.
5. Add bounded stream deadline, telemetry and mid-stream cleanup tests.
6. Run SNAP unit/protocol tests in CPython 3.9 image.
7. Run exact-source E.8.5/E.8.8 and G4 matrix.
8. Run the full-repository campaign and measure peak memory.
9. Add a detached verifier for the new M7.4 artifacts and record the evidence dossier.

No production, automatic backend-selection or scientific correctness claim is implied by completion of this transport work.

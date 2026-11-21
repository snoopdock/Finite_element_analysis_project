# AE-32C M6 — SNAP Isolated Worker: Implementation and Acceptance

**Status:** implementation committed; native conformance and repository parity are pending the current Stage1 workflow run. This record is not an acceptance declaration.  
**Target branch:** `stage1/section-uuids`  
**Implementation snapshot:** `7771d637cd613bf5cfc8c847108cd0c6eb28c98f`  
**Current E.8.5 / E.8.8 run:** [44914650206](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44914650206) — in progress at the time this record was written.  
**Main-branch change boundary:** only the E85 workflow controller was updated to launch the Stage1 implementation; SNAP adapter and worker source remain on Stage1.

---

## 1. Purpose and acceptance boundary

SNAP 6.0 is not imported into the project's Python 3.11 interpreter. The main orchestrator remains on Python 3.11; a separate CPython 3.9 process runs SNAP inside a restricted Docker container.

The worker is a computational projection only. The canonical `SemanticGraph`, graph fingerprint, edge-occurrence identities, evidence interpretation, traversal ordering, bounds, reference parity and repository source follow-through remain controlled by the Python 3.11 orchestrator.

The following are distinct states:

1. **Implementation present:** the worker protocol and proxy adapter exist.
2. **Runtime compatibility:** the pinned SNAP 6.0 wheel imports and its required TNEANet methods work in the worker.
3. **Synthetic native conformance (E.8.5):** exact projection round-trip, parallel-edge identity, self-loop behavior, native local adjacency and repeated query parity pass.
4. **Repository-backed conformance (E.8.8):** context tools use the worker's native adjacency; canonical parity, provenance, and hash-bound source follow-through pass.
5. **Milestone acceptance:** the above reports and the required exact-commit validation profile pass on the same Stage1 SHA.
6. **Production approval:** remains false; M6 acceptance does not itself authorize production backend selection.

A passing Python 3.9 import smoke or a test-double protocol test is not native acceptance.

## 2. Process boundary

### 2.1 Orchestrator

The Python 3.11 process:

- validates and clones the canonical graph snapshot;
- serializes only JSON-compatible node and edge payloads;
- starts the configured worker image through Docker;
- binds every request to the canonical graph fingerprint;
- validates worker response schema, request ID, payload and edge occurrence;
- converts native edge records into canonical `NativeEdgeOccurrence` values;
- performs deterministic traversal and compares every query with the Python reference;
- performs repository evidence/source follow-through outside the worker.

The orchestrator does not import the SNAP module.

### 2.2 Worker image

Files:

- `.github/snap-worker/Dockerfile`
- `.github/environments/e85-snap-python39-requirements.txt`
- `tools/snap_worker.py`

The image uses CPython 3.9 and installs the pinned `snap-stanford==6.0.0` binary distribution. The Docker build needs network access to obtain its base image and wheel. **The running worker container is different:** it is launched with network disabled.

The Docker runtime policy is:

- `--network=none`;
- read-only container root filesystem;
- non-root UID/GID;
- all Linux capabilities dropped;
- no-new-privileges;
- no repository or host-data bind mount;
- no provider credentials passed into the container;
- explicit host environment reduced to `PATH` and `HOME`;
- memory limit 512 MiB, CPU limit 1, and PID limit 64;
- image is prebuilt and launched with `--pull=never`, so runtime startup does not pull code or images.

The workflow records the local worker image ID. The worker report records the image name/ID, Python version, SNAP distribution version and declared container policy.

This is process/container isolation on the GitHub-hosted runner, not a claim that the host runner or Docker daemon itself has no network or repository access.

## 3. Protocol

Protocol identifier: `ae32c/snap-worker/v1`  
Transport: UTF-8 JSON Lines over standard input/output. Standard output is reserved exclusively for protocol frames; SNAP diagnostics are redirected to standard error.

Allowed operations:

| Operation | Purpose |
|---|---|
| `init` | Accept one immutable graph snapshot and construct TNEANet |
| `audit` | Return a one-time full projection readback for construction-time validation |
| `adjacency` | Return exact incident edge occurrences for one semantic node and direction |
| `metrics` | Return native adjacency counters |
| `close` | Terminate the worker |

The worker rejects unknown operations, extra or missing fields, invalid request IDs, protocol-version mismatch, graph-fingerprint mismatch, unknown semantic node IDs, invalid directions and malformed occurrence identities.

Resource bounds in the worker:

- maximum JSON line: 16 MiB;
- maximum nodes: 200,000;
- maximum edge occurrences: 1,000,000;
- maximum adjacency response: 100,000 edge occurrences.

The host adapter also rejects requests exceeding 16 MiB. These are hard limits, not performance targets.

## 4. Native TNEANet semantics

The worker assigns internal non-negative integer IDs to semantic nodes and preserves a separate mapping back to semantic string IDs. Each semantic edge occurrence is inserted as a distinct TNEANet edge, including parallel edges with identical endpoints and relation types.

The worker uses native incident edge IDs:

- outgoing: `TNEANetNodeI.GetOutEId(index)`;
- incoming: `TNEANetNodeI.GetInEId(index)`;
- edge inspection: `TNEANet.GetEI(edge_id)`.

The native edge ID is not treated as a semantic identity. Each edge carries an integer `semantic_occurrence` attribute. The worker validates that attribute and reads the endpoints, relation, attributes and metadata back from TNEANet before returning the record. The orchestrator independently validates the occurrence ID and all semantic payload fields against its canonical graph.

For a bidirectional query, the worker unions incoming and outgoing native edge IDs. A self-loop is consequently returned once. Parallel edges remain distinct because the union key is the native edge ID, not the endpoint pair.

The worker stores attribute dictionaries as canonical JSON strings in SNAP string attributes. This is an explicit representation transformation; it is not permission to discard or coerce values. Unsupported non-JSON values fail before worker launch. The E.8.5 fixture exercises Unicode, nested values, booleans, nulls, parallel occurrences and a self-loop.

Official API references:

- [SNAP 6.0 Graph and Network Classes](https://snap.stanford.edu/snappy/doc/reference/graphs.html) — documents TNEANet and node/edge iterator APIs.
- [SNAP 6.0 TNEANet developer reference](https://mmds.org/snap/doc/snapdev-ref/d6/db6/classTNEANet.html) — documents explicit edge IDs and `GetEI`.
- [SNAP 6.0 TNEANet node reference](https://snap.stanford.edu/snap/doc/snapdev-ref/d4/de9/classTNEANet_1_1TNode.html) — documents native incident edge-ID accessors.

These references establish the intended API contract; only the exact-version workflow run can establish compatibility with the installed Snap.py wheel.

## 5. E.8.5 / E.8.8 integration

### E.8.5

`tools/gb03_native_backend_conformance.py` now refuses to report SNAP native conformance unless the selected adapter is the isolated worker adapter. The report requires:

- exact native projection round-trip;
- all seven fixture scenarios, each repeated;
- strict reference parity;
- zero query/parity failures;
- observed native SNAP adjacency calls;
- nonzero native edge-occurrence reads;
- worker runtime and image provenance.

### E.8.8

`tools/gb04_repository_backend_conformance.py` records the worker provenance from the traversal runtime report. The same repository-backed checks used by other backends apply to SNAP:

- context-tool routing through the selected backend;
- native adjacency telemetry for each required context operation;
- strict parity with the canonical reference;
- zero backend bypasses and parity failures;
- graph-to-source follow-through with hash verification.

The dedicated workflow now runs E.8.8 for NetworkX, SciPy and igraph in the pip matrix, graph-tool in its conda-forge environment, and SNAP through the isolated worker. Stage1 pushes affecting the adapter, worker, tests or workflow run this conformance workflow automatically. The `main` workflow remains a manual controller that explicitly checks out Stage1.

## 6. Tests and evidence still required

The protocol test `tests/semantic_graph/test_snap_worker_adapter.py` uses a fake process to test request/response framing, occurrence conversion, environment minimization and container launch flags. It is a unit test only; it cannot establish that SNAP itself is functioning.

The decisive evidence is the actual E.8.5 and E.8.8 workflow run, which builds the Python 3.9 worker image, starts the real SNAP library, and executes both runners. The workflow must complete successfully and both JSON reports must show `status=passed`. The reports must bind to the same source SHA as the job logs and include the worker image ID.

After the dedicated workflow passes, run the G9.42 manual validation profile against that exact Stage1 SHA. Only then can M6 be recorded as accepted. Keep `production_approval=false`.

## 7. Known limitations and follow-up

- The Python base image is currently referenced by the `python:3.9-slim-bookworm` tag; the workflow records the resulting image ID. Pinning the base image by immutable digest is a reproducibility improvement.
- The protocol is synchronous and line-oriented. The worker is resource-limited and the workflow has a job timeout, but the adapter does not yet implement a per-request wall-clock timeout.
- The worker receives a complete immutable graph snapshot during initialization. It does not receive repository paths, source files, provider tokens or LLM prompts.
- The native worker is a query engine only. It does not become an authority for evidence, provenance, source hashes or semantic identity.
- M6 acceptance does not establish that SNAP is faster or operationally preferable. Comparative benchmarking belongs to M7.

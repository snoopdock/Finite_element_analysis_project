# AE-32C M7.4 G4 — Git LFS payload provenance

**Status:** Local-cache payload verification implemented as a separately bound attestation; remote provenance and repository-wide atomicity remain unverified.  
**Branch:** `stage1/section-uuids`

## 1. Source-derived format contract

The Git LFS v1 pointer specification defines a UTF-8 text pointer smaller than 1024 bytes, with a version line first, sorted key/value lines, an `oid sha256:<lowercase-hex>` field, and a byte-size field. Git stores the pointer blob; the payload is held separately in the local LFS object store or transferred through an LFS server. See the official [Git LFS specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md) and [Batch API](https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md).

The project distinguishes:
- Git blob integrity: pointer bytes are verified as a committed Git blob by `GitObjectSourceProvider`.
- Payload integrity: a local payload is independently streamed and checked against both the pointer's SHA-256 OID and declared byte size.
- Payload provenance: whether the bytes came from a trusted remote or authorized source. A matching digest proves content identity, not who supplied it.
- Transaction consistency: whether all source and external payload reads formed one atomic repository-wide snapshot. This remains out of scope.

## 2. Implemented policy

New module: `audit_engine/semantic_audit/ae32c/lfs_payload_verifier.py`.

The verifier:
- accepts an explicit local LFS object-store root; it does not discover or fetch a remote;
- scans every regular committed blob through the pinned Git-object provider;
- parses canonical Git LFS v1 pointers conservatively and rejects malformed/unsupported encodings;
- resolves the standard sharded cache path `<oid[0:2]>/<oid[2:4]>/<oid>`;
- rejects symlinked cache path components and non-regular payload files;
- streams payload bytes in bounded 1 MiB chunks;
- checks exact byte size and SHA-256 against the pointer;
- checks file identity/metadata before and after reading to detect common replacement or mutation races;
- returns a report bound to `source_snapshot_id`, commit OID and source inventory digest;
- never runs Git LFS smudge, invokes credentials, or accesses a network endpoint.

The output reports `lfs_payload_verified=true` only when every discovered pointer has a verified local payload. An empty pointer inventory is a completed scan with no external payloads to verify. The report always retains `remote_payload_provenance_verified=false`, `atomic_snapshot_established=false`, and `production_approval=false`.

## 3. Adversarial tests

The new test module covers:
- valid pointer parsing and malformed/noncanonical fields;
- a valid binary payload with embedded NUL bytes;
- exact OID and size verification;
- missing payload abstention;
- corrupt payload abstention;
- symlinked cache-object rejection;
- attestation binding to the provider's exact source snapshot identity.

The test suite intentionally does not test network downloads. Remote retrieval is a separate capability and must not be introduced implicitly into source capture.

## 4. Limitations

- Local cache content can be verified for identity, but the verifier cannot authenticate the remote server or the historical chain by which the cache was populated.
- Pointer extension values are retained but not semantically interpreted; payload identity is bound to the required OID and size.
- It does not establish an atomic snapshot across Git objects and external LFS files.
- It does not recurse into submodule LFS stores.
- A cache payload that changes after verification can invalidate the attestation; downstream consumers must retain or reverify the same immutable payload bytes before use.
- The current verifier reads committed regular blobs through the provider API; peak memory remains bounded by the largest blob passed through that API, not by the 1 MiB payload hashing chunk. This is a known optimization target.

## 5. Acceptance gate

The G4 status may claim local payload integrity only when the verifier has scanned the exact pinned source tree and every discovered LFS payload is present and matches the pointer's SHA-256 and size. Missing or malformed data is abstention, not a pass.

The following remain invariant until separate work closes them:
- `submodule_content_verified=false`;
- `remote_payload_provenance_verified=false`;
- `atomic_snapshot_established=false`;
- `production_approval=false`.

## References

1. Git LFS, [Git LFS Specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md).
2. Git LFS, [Batch API](https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md).
3. Git LFS, [Configuration and skip-smudge behavior](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-config.adoc).


## 6. Exact-source validation record — 2026-11-26

Implementation and workflow integration commit: `450755cd72b2ea5a83ae9654d3185809ef0584f9`.

- **Source and graph workflow:** [45814194079](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45814194079) — success on the exact implementation commit.
- **LFS verifier tests:** 4 passed (valid local payload, missing/corrupt payload abstention, strict pointer parsing, symlink rejection).
- **Immutable Git-object provider tests:** 21 passed.
- **Remaining source, graph identity, provenance and publication test groups:** all passed.
- **Source/graph artifact:** [ae32c-source-graph-snapshot-45814194079-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45814194079/artifacts/15113804774); artifact SHA-256 `5b2f4700b20fa28b5e7f17deaa8fa197d468c55ae6ef8c89182b565ca2e1deca`.

Cross-platform and cost qualification:

- **Workflow:** [45814194031](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45814194031) — success on the same exact source commit.
- **Windows selected G4 suite:** 53 passed, 46 skipped.
- **Linux mutation and repository side-effect acceptance:** passed.
- **Cost characterization:** 10 repetitions; report verification returned `status=verified`; source and runner revisions both matched `450755cd72b2ea5a83ae9654d3185809ef0584f9`.
- **Cost report SHA-256:** `eab2b78d3bfae3cb3adaa8faa914a5e3ee7658f3147d5c1445f8a4825d747d77`.
- **Cost artifact:** [m7-4-g4-source-snapshot-cost-45814194031-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45814194031/artifacts/15113769463); artifact SHA-256 `0660df5ab0fc104970aa8691bdbcc7bdc0671fc95e0746c1cd4dd6b3cf6435b9`.

The native graph backend conformance workflow [45814193964](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45814193964) also succeeded on the same implementation commit.

An earlier run [45814103757](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45814103757) failed because its corruption fixture had the same byte length as the expected payload while the test asserted a size-mismatch error. The fixture was changed to a different length and the exact-source rerun passed. The verifier's behavior was correct in the first run; the failed assertion was in the test fixture.

These results establish local payload content verification for the explicit cache fixtures and cross-platform execution of the verifier. They do not establish trusted remote provenance, recursive submodule LFS verification, or atomicity across Git and LFS object stores. `submodule_content_verified=false`, `remote_payload_provenance_verified=false`, `atomic_snapshot_established=false`, and `production_approval=false` remain invariant.

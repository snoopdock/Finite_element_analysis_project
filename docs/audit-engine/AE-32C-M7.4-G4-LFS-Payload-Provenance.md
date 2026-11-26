# AE-32C M7.4 G4 — Git LFS payload provenance

**Status:** Local-cache payload verification implemented as a separately bound attestation; remote provenance and repository-wide atomicity remain unverified.  
**Branch:** \`stage1/section-uuids\`

## 1. Source-derived format contract

The Git LFS v1 pointer specification defines a UTF-8 text pointer smaller than 1024 bytes, with a version line first, sorted key/value lines, an \`oid sha256:<lowercase-hex>\` field, and a byte-size field. Git stores the pointer blob; the payload is held separately in the local LFS object store or transferred through an LFS server. See the official [Git LFS specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md) and [Batch API](https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md).

The project distinguishes:
- Git blob integrity: pointer bytes are verified as a committed Git blob by \`GitObjectSourceProvider\`.
- Payload integrity: a local payload is independently streamed and checked against both the pointer's SHA-256 OID and declared byte size.
- Payload provenance: whether the bytes came from a trusted remote or authorized source. A matching digest proves content identity, not who supplied it.
- Transaction consistency: whether all source and external payload reads formed one atomic repository-wide snapshot. This remains out of scope.

## 2. Implemented policy

New module: \`audit_engine/semantic_audit/ae32c/lfs_payload_verifier.py\`.

The verifier:
- accepts an explicit local LFS object-store root; it does not discover or fetch a remote;
- scans every regular committed blob through the pinned Git-object provider;
- parses canonical Git LFS v1 pointers conservatively and rejects malformed/unsupported encodings;
- resolves the standard sharded cache path \`<oid[0:2]>/<oid[2:4]>/<oid>\`;
- rejects symlinked cache path components and non-regular payload files;
- streams payload bytes in bounded 1 MiB chunks;
- checks exact byte size and SHA-256 against the pointer;
- checks file identity/metadata before and after reading to detect common replacement or mutation races;
- returns a report bound to \`source_snapshot_id\`, commit OID and source inventory digest;
- never runs Git LFS smudge, invokes credentials, or accesses a network endpoint.

The output reports \`lfs_payload_verified=true\` only when every discovered pointer has a verified local payload. An empty pointer inventory is a completed scan with no external payloads to verify. The report always retains \`remote_payload_provenance_verified=false\`, \`atomic_snapshot_established=false\`, and \`production_approval=false\`.

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
- \`submodule_content_verified=false\`;
- \`remote_payload_provenance_verified=false\`;
- \`atomic_snapshot_established=false\`;
- \`production_approval=false\`.

## References

1. Git LFS, [Git LFS Specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md).
2. Git LFS, [Batch API](https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md).
3. Git LFS, [Configuration and skip-smudge behavior](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-config.adoc).

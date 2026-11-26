# AE-32C M7.4 G4 — Immutable Git-object source reader design

**Status:** Design decision; implementation and exact-source execution pending.  
**Development branch:** `stage1/section-uuids`  
**Baseline:** `6fad135910d14dc47f086ec9d343eb1a7d04a265`

## 1. The gap being addressed

The current source manifest already obtains a commit tree inventory with `git ls-tree`, reads blob objects with `git cat-file --batch`, and binds path, mode, object ID and SHA-256 content digest. However, the repository evidence pipeline still calls the filesystem-oriented `audit_repository(root)`, then loads indexed source bytes from paths and performs a second filesystem validation. Consequently, the manifest's Git-object identity and the bytes consumed by graph construction are not yet one immutable read path.

The next change must connect the object inventory to the actual bytes parsed into the source graph. Adding a second manifest or recording Git object IDs without changing the graph's read path would not close this gap.

## 2. Scope and consistency classes

The source reader must expose an explicit consistency class:

- `IMMUTABLE_GIT_OBJECTS`: committed-tree entries and bytes are read from Git objects identified by one exact commit and root tree.
- `FILESYSTEM_SNAPSHOT`: a platform snapshot provider exposes one immutable filesystem view, identified by its snapshot ID.
- `BEST_EFFORT_NON_ATOMIC`: the existing live-tree scanner and handle/revalidation controls. It remains useful but cannot satisfy the atomic snapshot gate.

The first implementation targets `IMMUTABLE_GIT_OBJECTS` for committed source. It does not claim to snapshot dirty working-tree content. The selected scope must be recorded as `committed_tree_only`; it must never silently describe itself as a complete working-tree snapshot.

For committed-tree CI runs, bind the exact expected commit SHA and root tree SHA. If the caller requests working-tree scope, or if the workflow expects dirty/untracked inputs to be included, the Git-object provider must reject that request rather than substituting `HEAD`.

## 3. Source-reader contract

Introduce a small provider interface used by both the architecture audit and repository evidence builder:

- `snapshot_identity()`: returns schema version, consistency class, repository identity, commit OID, root tree OID, object-hash algorithm, inventory digest and declared source scope.
- `iter_entries()`: yields every tree entry in deterministic UTF-8 path order, including path, mode, object type and object ID.
- `read_entry(path)`: returns bytes only for an included regular-file blob, after verifying the returned object type, object ID and SHA-256 digest against the inventory.
- `entry_metadata(path)`: returns the immutable identity and materialization class for the entry.
- `coverage_report()`: reports included, excluded, unsupported, unaccounted and unverified object entries with explicit reasons.

The provider must not resolve repository paths through the host filesystem when reading included source bytes. The Git object database is the source of bytes. No target repository module may be imported or executed.

## 4. Git object inventory rules

Use the exact commit and root tree supplied by the caller. Resolve and validate them before scanning:

1. Resolve the full commit OID; reject abbreviated or ambiguous revisions at the trusted boundary.
2. Resolve `commit^{tree}`; record the root tree OID and object format.
3. Enumerate recursive tree entries using NUL-delimited Git output; preserve exact path bytes and reject unsupported path encoding rather than silently replacing characters.
4. For regular blobs, bind path, mode, blob OID, byte length and SHA-256 of blob content.
5. For symlink mode `120000`, retain the blob identity and link-target bytes as metadata; do not follow the link or treat its target as a file path.
6. For gitlink mode `160000`, record the submodule commit pointer and report submodule content as outside this provider's recursive scope unless a separately pinned submodule provider is implemented.
7. Detect Git LFS pointer blobs. Hash the Git blob pointer as stored, but mark external LFS payload bytes as unverified; do not claim to have audited the hydrated object.
8. Reject unexpected tree modes/object types and duplicate paths.
9. Sort entries by raw path bytes for deterministic inventory identity.

The existing source manifest's `git cat-file --batch` implementation is a useful starting point, but the new provider must return verified bytes to the graph builder, not only a digest map.

## 5. Graph and evidence binding

Every derived artifact must carry the same `source_snapshot_id` and inventory digest:

- source inventory;
- parsed file-content index;
- semantic graph snapshot;
- graph coverage report;
- findings/evidence ledger;
- task execution report;
- publication candidate, if one is later prepared.

The graph builder must receive the provider as its only source of included file bytes. It must not mix Git-object bytes with filesystem bytes in one graph build. If any included object cannot be read or verified, graph construction must fail or mark the relevant scope incomplete and abstain according to the rule contract.

The existing file content hashes should be the SHA-256 values of the exact bytes returned by the provider. Source line/column references are computed from those bytes. A later source-follow-through operation must read the same blob identity, not reopen an unpinned working-tree path.

## 6. Integration boundary

The current `RepositoryEvidenceTools` constructor performs these operations in sequence:

1. `audit_repository(self.root)`;
2. `_load_indexed_content()`;
3. `_validate_loaded_source_snapshot()`;
4. `_build_graph()`.

The implementation should refactor the source boundary so that the audit inventory and content loader share one provider instance. The filesystem provider can preserve existing behavior and report `BEST_EFFORT_NON_ATOMIC`. The Git provider must provide both inventory and bytes from the object database. Avoid a parallel implementation in which the manifest uses Git objects but the parser still reads the worktree.

The audit scanner's parsing and semantic extraction logic should be reused; only enumeration and byte acquisition should vary by provider. Any path-dependent configuration must be read through the same provider, or explicitly declared as external runner configuration and excluded from repository source scope.

## 7. Required adversarial tests

### Object identity and content

- exact commit and root-tree binding;
- blob OID mismatch and SHA-256 mismatch;
- truncated `cat-file` response and malformed object header;
- duplicate path, unsupported mode and unsupported object type;
- non-UTF-8 path behavior (explicit rejection or documented byte-safe support);
- symlink target is never followed;
- gitlink is represented as a pointer, not recursively trusted;
- LFS pointer is distinguished from hydrated payload;
- large blobs are streamed with bounded memory.

### Mutation independence

- modify, rename or delete a worktree file after provider construction; Git-object bytes remain unchanged;
- replace a path with a symlink or hard link; object reads remain bound to the tree entry;
- mutate and restore worktree content (ABA); object-backed graph remains byte-identical;
- alter index and untracked files; committed-tree graph remains identical while scope report says they are excluded;
- mutate the Git ref after resolving the commit; provider remains bound to the resolved commit/tree OIDs;
- garbage-collect or remove an object during provider use; read fails closed and does not fall back to filesystem bytes.

### Cross-artifact provenance

- graph, source inventory, coverage, finding ledger and task report all carry identical source snapshot identity;
- a mixed snapshot identity is rejected;
- a missing source entry or unsupported object causes explicit incomplete coverage/abstention;
- source-follow-through verifies exact object identity and content digest.

Run the provider tests on Linux and Windows. The provider's Git subprocess behavior and path-byte handling must be qualified on both supported runner families.

## 8. Acceptance boundary

The implementation can claim `IMMUTABLE_GIT_OBJECTS` only after the graph builder consumes bytes from the provider and all derived artifacts bind the same snapshot identity. Passing provider unit tests alone is not enough.

The following remain separate and unresolved:

- a point-in-time snapshot of dirty/untracked working-tree content;
- platform filesystem snapshots;
- recursive submodule content;
- hydrated Git LFS payloads;
- race-free source-follow-through against a mutable checkout;
- atomicity of the complete audit transaction beyond the immutable committed-object scope.

Until the above integration and tests pass, G4 remains **Partial** and `atomic_snapshot_established=false`. The existing filesystem path remains explicitly `BEST_EFFORT_NON_ATOMIC`; no code path may silently upgrade its status.

`production_approval=false` remains invariant.

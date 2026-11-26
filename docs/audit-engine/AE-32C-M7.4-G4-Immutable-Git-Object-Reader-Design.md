# AE-32C M7.4 G4 — Immutable Git-object source reader design

**Status:** Implemented for committed-tree graph construction; exact-source Linux and Windows validation passed. Broader atomicity gates remain open.  
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


## 9. Implementation and exact-source validation record

The first integrated implementation is committed on \`stage1/section-uuids\`:

- **Commit:** \`159354d9444695b66fed468fbf8ad4d2cdc1c4ac\`
- **Workflow run:** [45796042025](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45796042025)
- **Workflow result:** success
- **Artifact:** [ae32c-source-graph-snapshot-45796042025-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45796042025/artifacts/15105580104)
- **Artifact SHA-256:** \`a9b8d2e24839bf019adee10506d82ec1686ff317e8549652d02f3c868315391c\`

The implementation adds \`GitObjectSourceProvider\` at \`audit_engine/semantic_audit/ae32c/git_object_source.py\`. It verifies the source manifest and its inventory digest, checks the exact commit and root tree against the local Git object database, compares the complete NUL-delimited Git tree inventory with the manifest, and reads regular-file bytes by blob object ID. It verifies both the Git blob object ID and the SHA-256 digest before returning bytes. It rejects symlink reads and does not silently fall back to worktree paths.

The same provider instance is passed into AE-32A's \`audit_repository\` and AE-32B's \`RepositoryEvidenceTools\`. The architecture scanner's committed-tree inventory and the graph evidence content loader therefore consume the same Git-object source. The second source-validation pass rereads the pinned Git objects rather than reopening repository paths. The provider declares its consistency class as \`IMMUTABLE_GIT_OBJECTS\` and its scope as \`committed_tree_only\`.

Graph coverage now rejects any represented path or file-hash key that is absent from the committed Git inventory. Existing missing-source accounting remains in place. The source snapshot workflow now runs the provider tests and is restricted to push and pull-request events for \`stage1/section-uuids\`; the documented branch scope is aligned with the workflow.

### Exact-source execution result

The successful run checked out the exact commit above and passed:

- source snapshot manifest unit tests;
- immutable Git-object provider tests (ignored/untracked exclusion, worktree mutation independence, manifest/tree mismatch);
- graph snapshot identity and coverage tests, including rejection of extra uncommitted graph paths;
- rule coverage and finding-provenance tests;
- publication state-machine tests;
- durable GitHub publication backend tests;
- trusted artifact validation tests;
- trusted publisher orchestration tests;
- end-to-end graph snapshot capture;
- source postflight verification after graph projection.

The graph snapshot reported:

- source snapshot ID: \`03528e4f05c028d43234da54c1c527a5c1d6033e39cc59259340028f1c9a8dc3\`;
- graph snapshot ID: \`b228fd1fc3883f8c5614be51d26d4489636b24c793b50575d050d492967d34d9\`;
- graph content SHA-256: \`ec5e91549aff324ab0a259c31b14ddab5f314b2b034be4249834ea52962d48dc\`;
- committed inventory entries: 1,970;
- represented source units: 1,902;
- unaccounted source units: 0;
- coverage: \`COMPLETE_WITH_DECLARED_EXCLUSIONS\`;
- source postflight: \`VERIFIED\`.

### Remaining limits

This implementation closes the mixed filesystem/Git-object read path for the committed-tree graph build. It does not establish a snapshot of dirty or untracked working-tree content, recursive submodule content, hydrated Git LFS payload integrity, or an atomic snapshot of all external filesystem state. The provider tests now include ignored/untracked exclusion, worktree mutation independence, manifest/tree mismatch, symlink non-following and Git LFS pointer classification. The integrated workflow has been executed on Ubuntu 24.04; Windows qualification remains pending. The graph coverage status is still constrained by its declared exclusions and does not authorize negative findings by default.

Accordingly, this implementation advances G4 from partial source identity binding to an integrated immutable committed-tree source path, but does not authorize production approval. \`production_approval=false\` remains invariant.


## 10. Follow-up hardening and cross-platform validation

The implementation was hardened and revalidated on the later Stage1 source revision:

- **Stage1 commit:** \`308e3cb6fe35099bfe8b85af2784a5cca4f4b101\`
- **Source/graph workflow:** [45797000319](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45797000319) — success
- **Windows and cost workflow:** [45797000329](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45797000329) — success
- **Windows result:** 33 passed, 46 skipped across the provider and existing source-snapshot/lifecycle test selection
- **Cost report artifact:** [m7-4-g4-source-snapshot-cost-45797000329-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45797000329/artifacts/15105711296)
- **Cost artifact SHA-256:** \`796de7abd8a6aee895f47537d6e3709f07df5a100870a37c51a18e278704b9da\`

The provider now identifies Git LFS pointer blobs when their committed bytes are read and reports the pointer paths separately; it explicitly keeps \`lfs_payload_verified=false\`. Graph coverage now treats only regular Git blobs as eligible represented source paths, rejecting graph paths that point to symlinks or gitlinks as well as paths absent from the committed tree. The Windows workflow executes the Git-object provider tests; symlink-specific test setup is skipped only where the host does not permit creating symlinks.

The exact-source graph run reported:

- source snapshot ID: \`f74a062bb4638bac51add1513e40965efc8741826fedfcbe043844bea149feae\`;
- graph snapshot ID: \`6e9f41db6b8dd169df12244c67b9b8e2d0a1f897dd6450100b01ef68a6b36941\`;
- graph content SHA-256: \`ea48f39fc4707889ca10ad4422ccfd721997b9091696af047109daebbf73bf74\`;
- source inventory entries: 1,970;
- represented source units: 1,902;
- unaccounted source units: 0;
- coverage: \`COMPLETE_WITH_DECLARED_EXCLUSIONS\`;
- postflight source status: \`VERIFIED\`.

The cost-characterization workflow completed ten repetitions and verified its report against the exact source and runner revision. Its report explicitly retained \`atomic_snapshot_established=false\`; this is expected and is not a failed source-identity check. It measures the existing filesystem audit/content-load/second-validation path, not a comparative performance claim for graph libraries or a complete benchmark of the Git-object provider.

The separate M7.4 native-conformance workflow also completed successfully on this source revision for NetworkX, igraph, SciPy, graph-tool and the isolated SNAP worker.

The implementation therefore has Linux and Windows evidence for the committed Git-object provider and end-to-end graph construction. The remaining exclusions are still material: working-tree/dirty input snapshots, recursive submodule contents, hydrated LFS payloads, and repository-wide atomicity beyond the immutable committed-object boundary. Production approval remains false.


## 11. Adversarial provider qualification — 2026-11-26

The provider test suite was extended to exercise failure and race boundaries that were previously design requirements but not executable tests:

- pinned Git ref movement after provider construction;
- worktree ABA mutation (mutate, restore, then read the pinned object);
- hard-link replacement of a worktree path;
- missing pinned blob object;
- corrupt pinned blob object;
- a real local submodule/gitlink entry, which must not be read as a regular blob;
- existing ignored/untracked exclusion, worktree mutation independence, symlink rejection, LFS pointer classification, and manifest/tree mismatch.

The first Windows execution exposed two test portability assumptions: Git loose objects are read-only on the Windows runner, and checkout line-ending conversion can make worktree bytes differ from canonical Git blob bytes. The tests were corrected to make the loose object writable before deletion and to assert the committed blob bytes—not the platform checkout representation—after ABA restoration. No production-provider fallback or weakening was introduced.

### Exact-source validation

- **Stage1 commit:** \`f75eb091a11a25dee178b41caba232afe37b3e93\`
- **Source/graph workflow:** [45805302622](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45805302622) — success
- **Windows and cost workflow:** [45805302513](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45805302513) — success
- **Linux provider tests:** 11 passed
- **Windows provider and source-snapshot selection:** 39 passed, 46 skipped
- **Cost characterization:** 10 repetitions; report verified against the exact source and runner revision
- **Cost report SHA-256:** \`8287298799b6a7c776cc23c3e5713a8c023fb634ebf09f2998451b3456f7de73\`
- **Cost artifact:** [m7-4-g4-source-snapshot-cost-45805302513-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45805302513/artifacts/15108594147)
- **Cost artifact SHA-256:** \`0e12ba075a194c737b29cb5125651333dd01e9a86518be7bf99b6f116eff19c4\`
- **Source/graph artifact:** [ae32c-source-graph-snapshot-45805302622-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45805302622/artifacts/15109565809)
- **Source/graph artifact SHA-256:** \`89f086be0827833d6ec17721e3fb6f96c3d77ce3d124b3bfcaa41a8d061fb260\`

The exact-source graph capture reported:

- source snapshot ID: \`fb47b6fb2defd2cd18b67bb14986e4ba8324dfa102ea336d5c939edfd19e64bd\`;
- graph snapshot ID: \`4e549cc46cbb1b0bd1621403feca4121791000a675883f6bfaa57bc9cc8b71f7\`;
- graph content SHA-256: \`1229137f5363b2a4585b12cc9a240ffb10aee4f8fa4e80e394420df3d331e5ea\`;
- source inventory entries: 1,970;
- represented source units: 1,902;
- unaccounted source units: 0;
- coverage: \`COMPLETE_WITH_DECLARED_EXCLUSIONS\`;
- source postflight: \`VERIFIED\`.

The cost report explicitly retains \`atomic_snapshot_established=false\`. The result characterizes the existing repository audit/content-load/second-validation path; it is not evidence that the full audit transaction has become atomic.

These tests strengthen confidence in the immutable committed-tree boundary. They do not close the separately declared exclusions: dirty/untracked working-tree snapshots, recursive submodule content, hydrated LFS payloads, and repository-wide transaction atomicity. \`production_approval=false\` remains invariant.


## 12. Git subprocess environment isolation — 2026-11-26

A further object-database review identified that both source-manifest capture and the immutable provider inherited the caller's Git environment. This left the Git interpretation dependent on ambient variables that can redirect repository discovery or object lookup, and did not explicitly suppress replacement-object semantics or partial-clone lazy fetching.

The source-capture utility and provider now construct a controlled environment for every Git subprocess:

- remove inherited variables whose names begin with `GIT_`, including repository/object-directory routing, namespace, replacement-policy overrides, and command-scope configuration injection;
- set `GIT_NO_REPLACE_OBJECTS=1`, so `refs/replace/*` cannot substitute another object for the pinned OID;
- set `GIT_NO_LAZY_FETCH=1`, so a missing promisor object cannot be fetched implicitly during capture or reading;
- disable optional locks and system/global Git configuration for deterministic subprocess behavior.

The source manifest's streaming `cat-file --batch` process uses the same environment policy as its other Git commands. The provider uses the same policy for commit/tree resolution, inventory enumeration, blob type/content reads, and object-ID verification.

### Added adversarial tests

The provider test suite now includes:

- a replacement ref mapping the pinned commit to a different commit; provider construction and reads must still resolve the literal pinned commit and its original committed bytes;
- inherited `GIT_DIR`, `GIT_WORK_TREE`, `GIT_OBJECT_DIRECTORY`, `GIT_NO_REPLACE_OBJECTS=0`, and `GIT_NO_LAZY_FETCH=0`; manifest capture and provider construction must remain bound to the requested repository;
- a SHA-256-format Git repository, where supported by the installed Git version, to verify object-format-aware commit, tree and blob identity handling.

### Implementation revisions

The changes were applied only to `stage1/section-uuids`:

- provider environment isolation: `faa0f2f8d61c86896e6b50a615cb1e7df3ee21ec`;
- source-manifest environment isolation: `adc8ce3849544aa92f4cff8e11add4ea027c8048`;
- replacement-ref, inherited-environment and SHA-256 tests: `60c4b913f70404eb5fae8b598da828aafa894c7d`.

**Validation status at documentation time:** GitHub Actions execution for the new source revision is pending inspection. These commits are implementation evidence, not a test-pass claim.

### Remaining object-database qualification

The following cases remain open and must not be inferred as solved by environment isolation:

- on-disk alternates configured through `.git/objects/info/alternates`; inherited `GIT_ALTERNATE_OBJECT_DIRECTORIES` is removed, but repository-configured alternates are still part of Git's object lookup and their provenance policy has not yet been accepted or rejected;
- shallow repositories and graft files; the current provider reads the pinned commit's tree and does not traverse history, but the boundary behavior still needs executable qualification;
- partial-clone/promisor repositories; lazy fetch is disabled, but an adversarial missing-promisor-object test has not yet demonstrated the fail-closed behavior;
- concurrent object disappearance or replacement during an in-flight read;
- repository SHA-256 compatibility on each supported CI runner family.

The next pass should test these cases directly, distinguish immutable content identity from object-database provenance, and record the resulting trust boundary. `atomic_snapshot_established=false` and `production_approval=false` remain invariant.

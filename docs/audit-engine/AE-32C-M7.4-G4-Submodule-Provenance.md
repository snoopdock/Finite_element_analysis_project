# AE-32C G4 — Submodule provenance boundary

**Status:** Pointer-level provenance is now explicit in the immutable Git-object provider. Recursive submodule content verification is not implemented.  
**Branch:** `stage1/section-uuids`  
**Baseline:** `b478cd37fb516beafbab4c07e43a1296eccc11fb`

## 1. Why a gitlink is not a submodule snapshot

A superproject tree records a submodule as a gitlink (mode `160000`) whose object name identifies the commit expected in the submodule repository. Git's documentation describes the gitlink as the commit expected for the submodule working directory; the submodule itself has its own history and repository. Consequently, the superproject tree proves the selected commit pointer, not the files or nested submodules reachable from that commit.

Primary references:

- [Git: gitsubmodules](https://git-scm.com/docs/gitsubmodules) — superproject/gitlink model.
- [Git: git-submodule](https://git-scm.com/docs/git-submodule) — update checks out the commit recorded by the superproject; recursive operation is explicit.
- [Git: gitmodules](https://git-scm.com/docs/gitmodules) — URLs and update configuration; URL values can be configured locally and are not a trust certificate.

The provider must therefore distinguish:
1. **Pointer verification:** the exact path, mode, object type and commit OID are part of the pinned superproject tree and source inventory.
2. **Submodule content verification:** the target commit object, its complete tree, blobs, nested gitlinks and LFS pointers have been independently resolved and verified in the submodule repository.

Only (1) is established by the existing superproject inventory.

## 2. Security and provenance policy

The current implementation adopts a deliberately bounded policy:

- Do not fetch, clone, initialize, update, checkout, or execute anything from a submodule URL during source capture.
- Do not trust `.gitmodules`, local `.git/config`, an initialized worktree, or a matching directory as proof of content identity.
- Do not read a gitlink with the regular-file blob API.
- Preserve each gitlink's path and expected commit OID in the coverage report.
- Report the content state as `UNVERIFIED_EXTERNAL_REPOSITORY`; use `POINTER_ONLY_NO_NETWORK_NO_CHECKOUT` as the explicit resolution policy.
- Keep `submodule_content_verified=false` even when the submodule path exists locally.

This avoids conflating a repository-controlled URL with trusted provenance and avoids hidden network resolution during an audit. Git documents that submodule update can clone/fetch missing commits and check out the superproject-recorded commit; recursive mode can descend into nested submodules. Those operations are intentionally outside the source-reader's current trust boundary.

## 3. Implemented provider contract

`GitObjectSourceProvider` now materializes a deterministic `submodule_entries` list from the verified superproject tree inventory. Each record contains:

- `path`;
- `expected_commit_oid`;
- `pointer_status=SUPERPROJECT_GITLINK_VERIFIED`;
- `content_status=UNVERIFIED_EXTERNAL_REPOSITORY`;
- `recursive_content_verified=false`.

`coverage_report()` exposes the count, records, and explicit no-network/no-checkout policy. A gitlink continues to fail the regular-file `read_entry` contract. A repository with no gitlinks reports an empty list; absence of gitlinks is not presented as proof of recursive verification.

## 4. Structural and behavioral tests

The provider test suite adds two tests:

1. Create a real index gitlink (mode `160000`) pointing to a commit, commit the superproject, capture and verify its manifest, then assert that the provider reports the exact expected commit pointer while retaining the external-content-unverified status. A read through the regular-file API must fail closed.
2. Assert that a repository with no gitlinks reports an empty submodule inventory and still leaves `submodule_content_verified=false`.

These tests verify both the positive representation of a gitlink and the negative boundary against silently treating it as audited source.

## 5. Current repository inventory finding

At baseline `b478cd37fb516beafbab4c07e43a1296eccc11fb`, the recursive Git tree contains **no mode-160000 entries** and no root `.gitmodules` file. Thus the current project source tree does not exercise a real submodule dependency. The synthetic gitlink fixture is necessary to test the provider's behavior if one is introduced later.

This finding is specific to the pinned branch revision; it is not a claim about every historical commit or external checkout.

## 6. Acceptance boundary and next tranche

This change establishes **explicit pointer accounting**, not recursive submodule verification. G4 must continue to report:

- `submodule_content_verified=false`;
- `lfs_payload_verified=false`;
- `atomic_snapshot_established=false`;
- `production_approval=false`.

A future recursive verifier requires a separately specified repository identity and trust policy for every submodule, exact commit resolution without branch movement, object-format-aware inventory and blob verification, bounded recursion/depth and cycle handling, rejection of missing/promisor/alternate object stores under the same policy, and recursive treatment of nested gitlinks and LFS pointers. It must not rely on a worktree checkout as its source of bytes.

Only after that verifier is implemented and exercised on real nested-submodule fixtures on Linux and Windows may the status be upgraded. The next independent target after this pointer-accounting tranche is hydrated Git LFS payload provenance, followed by repository-wide transaction consistency.

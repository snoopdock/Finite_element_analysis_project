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


## 7. Exact-source cross-platform validation — 2026-11-26

Implementation commit: `7027b5bf0aa0c18d6180c37695ecea7090d69eb9`.

### Immutable provider and graph snapshot

- **Workflow:** [45812297850](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45812297850) — success on the exact implementation commit.
- **Linux immutable-provider suite:** 21 passed, including the real initialized-submodule fixture and all prior adversarial object-database cases.
- **Source inventory:** 1,971 entries; inventory SHA-256 `bf89d9524470905264b5000ea2814531a39689a6bea91afb1161d54d0568fbc1`.
- **Source snapshot ID:** `6eeb4fda92cf43f2ff2f6f1cc0fd7eea176b6123842bd302166a4ffec3aeaba2`.
- **Graph snapshot ID:** `006c95a081292d2840b50d724f4f3511a27b4873e9818db7c4ea58e4fb738a22`.
- **Graph content SHA-256:** `38f4d390b124c31c5e9fdb558b20ef76eee72ef60be380c224bfc24b2adb605a`.
- **Graph coverage:** 1,903 represented source units; zero unaccounted units; `COMPLETE_WITH_DECLARED_EXCLUSIONS`.
- **Source postflight:** `VERIFIED`.
- **Source/graph artifact:** [ae32c-source-graph-snapshot-45812297850-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45812297850/artifacts/15114297316), Actions SHA-256 `26b981a1180f59f69b52cf7b5ff310a6e48f74fa636140b4d47db34a418d4276`.

### Windows and cost qualification

- **Workflow:** [45812297784](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45812297784) — success on the exact implementation commit.
- **Windows source/provider and selected G4 suites:** 49 passed, 46 skipped. Skips are backend-selection/platform-specific cases in the combined selection; the run completed successfully.
- **Linux repository mutation/side-effect acceptance:** passed.
- **Cost characterization:** 10 repetitions; report verification returned `status=verified`; source and runner revisions both matched the implementation commit.
- **Cost report SHA-256:** `a2a196558333adb94d4d4b4fc1681041855a69bd6ac76be46cccb9ae9152f39b`.
- **Cost manifest SHA-256:** `f8f3bb4e007e3fcd41ad9098a51cfe886c9d62a281c28ded8a497d21e027ca6b`.
- **Cost artifact:** [m7-4-g4-source-snapshot-cost-45812297784-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45812297784/artifacts/15113627530), Actions SHA-256 `88ceabdca137de4ef09c43d43206c98ee8fb8ba63047dd6be294d653369f332d`.

### Native backend regression

The full E.8.5/E.8.8 native backend workflow [45812298248](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45812298248) also completed successfully on the same implementation commit. NetworkX, SciPy, igraph, graph-tool and isolated SNAP jobs all passed, including their existing G4 snapshot/mutation and repository side-effect suites. This is regression evidence for the wider audit engine; it is not a claim that the submodule provider recursively audits submodule content.

The submodule boundary is therefore implemented and tested on Linux and Windows as **pointer accounting with explicit content abstention**. Recursive submodule content remains unverified. `submodule_content_verified=false`, `lfs_payload_verified=false`, `atomic_snapshot_established=false`, and `production_approval=false` remain invariant.

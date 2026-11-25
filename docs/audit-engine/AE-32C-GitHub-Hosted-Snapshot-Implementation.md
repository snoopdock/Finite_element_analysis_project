# AE-32C — GitHub-Hosted Source Snapshot and Audit-Run Identity

**Status:** Initial implementation specification and operator guide  
**Implementation tranche:** Source identity and manifest (Phase 1)  
**Target branch:** stage1/section-uuids  
**Architecture inputs:** Revised Notes 001–006, Iterations 11–15  
**Authority:** Git commit/tree for committed source; derived graph and audit results are separately identified  
**Production approval:** Not granted

## 1. Purpose and scope

This document specifies the first GitHub-hosted implementation unit for the repository audit engine. It establishes an exact source identity, captures a Git-tree inventory, verifies the runner worktree before and after the workflow's snapshot interval, and retains a compact JSON manifest as a GitHub Actions artifact.

The implementation deliberately does not introduce:

- a permanent second copy of the repository;
- an external object-storage dependency;
- a graph database or persistent graph archive;
- incremental graph recomputation;
- LLM or solver orchestration;
- automated remediation or merging;
- a claim of atomic multi-file filesystem snapshot semantics.

The first tranche provides a trustworthy identity boundary for later graph, audit, LLM, solver and remediation records. It is not a complete audit-engine qualification.

## 2. Relationship to the six architecture notes

| Source note | Requirement carried into this implementation |
|---|---|
| 001 — Graph-native audit engine | Source facts remain authoritative; derived graph identity and coverage must be separate |
| 002 — Activation and incremental recomputation | Events activate runs; exact snapshots define runs; cache and event payloads are not source authority |
| 003 — Pluggable LLM integration | Any later model output must be bound to this run/source/evidence identity and remain non-authoritative |
| 004 — Quantifying remediation decisions | Any later patch must identify and verify its exact base source revision |
| 005 — Formal solver portfolio | Any later solver input/result/certificate must bind to the exact source and encoding |
| 006 — Self-examination and termination | Run identity, protected verification boundaries and explicit incomplete/failure states are required |

This implementation only establishes the source-level part of that contract. It must not be represented as satisfying graph-coverage, publication-consistency, solver, remediation or trusted-kernel requirements in full.

## 3. Source identity

The authoritative committed source is identified by:

- repository name;
- event/source mode;
- commit object ID;
- Git object-ID algorithm;
- root tree object ID;
- base and head commit IDs for pull requests;
- SHA-256 digest of a canonical source inventory.

The inventory includes each recursively listed Git tree entry's path, mode, object type, Git object ID, materialization kind and SHA-256 digest of the canonical Git blob bytes.

The inventory digest is calculated over canonical JSON using UTF-8, sorted object keys, compact separators, no NaN or Infinity values, deterministic path ordering and a final newline. The Git object ID remains the native Git identity. The SHA-256 inventory digest is an additional digest over the listed entries, not a replacement for commit/tree identity.

### 3.1 Pull-request modes

The initial workflow uses the GitHub pull_request event and checks out github.sha, which represents the event's merge revision. The manifest records:

- commit_oid: exact checked-out merge revision;
- base_commit_oid: pull request base SHA from the event payload;
- head_commit_oid: pull request head SHA from the event payload;
- event_merge_commit_oid: merge SHA reported in the event payload, if present.

This is an integration snapshot. It is not a head-only change audit. A future change-audit workflow must explicitly check out and identify base and head revisions and must not relabel the merge result as the head.

### 3.2 Object types and exclusions

- Ordinary and executable files are represented by Git blob object and mode.
- Symlinks use Git mode 120000; the digest covers the Git blob containing the link target, not target-file bytes.
- Submodules use mode 160000 and their gitlink commit ID. This implementation does not recursively materialize or verify submodule worktrees.
- Git LFS pointer blobs are hashed as Git objects. The external LFS payload is not independently fetched or verified by this first tranche.
- Paths that are not valid UTF-8 fail closed. Supporting arbitrary byte paths requires a versioned byte-safe inventory schema.

These limitations are explicit and must not be hidden behind a generic VERIFIED label.

## 4. Capture and postflight protocol

The workflow performs the following operations:

1. Checkout the exact event revision with persisted checkout credentials disabled.
2. Run source-manifest unit tests.
3. Capture commit, root tree, object format and recursive Git-tree inventory.
4. Verify that the checkout commit equals github.sha.
5. Require a clean worktree at capture.
6. Write the manifest under RUNNER_TEMP, outside the repository.
7. Recompute source identity and inventory after the capture interval.
8. Require the same commit, root tree, inventory digest and clean worktree.
9. Update the manifest to VERIFIED only when postflight checks pass.
10. Upload the manifest as a compact Actions artifact.

The output directory is outside the repository checkout so evidence generation does not create untracked files inside the source tree.

### 4.1 What VERIFIED means

For this version, VERIFIED means:

- the checked-out commit matched the expected event SHA;
- the root tree and canonical inventory were recorded;
- Git blob bytes were SHA-256 hashed;
- the worktree was clean at capture;
- the same source identity and inventory were observed at postflight;
- the worktree was clean at postflight.

It does not mean:

- all repository files existed in one atomic filesystem instant;
- no file changed and was restored between checks;
- every submodule or LFS payload was materialized and checked;
- no external filesystem side effect occurred;
- the semantic graph is complete;
- every audit rule is sound;
- the result is current for a mutable branch at publication time.

A successful two-pass check narrows and detects tested persistent changes. It does not establish an atomic multi-file snapshot or eliminate ABA mutation schedules.

## 5. Manifest schema

The JSON Schema is maintained at:

docs/audit-engine/schemas/ae32c-source-snapshot-manifest-v1.schema.json

The generated manifest contains:

- manifest_schema: schema identifier;
- manifest_sha256: canonical digest of the manifest excluding this field;
- status: capture/postflight state;
- source_snapshot_id: digest of source identity fields;
- source: repository, commit, tree, object format and PR identities;
- event: event name, ref and source mode;
- source_inventory: entries and inventory digest;
- materialization: worktree state and known exclusions;
- verification: capture/postflight comparison;
- run: GitHub workflow run identity;
- authority: explicit non-claims.

The manifest is a historical run record after artifact upload. A later publication decision should be a separate record; it must not rewrite source facts or computation history.

## 6. Workflow and permissions

Workflow:

.github/workflows/ae32c_source_snapshot_manifest.yml

The workflow:

- runs on pushes to stage1/section-uuids;
- runs on pull requests targeting stage1/section-uuids;
- supports manual dispatch;
- requests contents: read only;
- disables persisted checkout credentials;
- pins checkout to a full commit SHA;
- uses a 15-minute job timeout;
- writes artifacts under the runner temporary directory;
- retains the compact manifest artifact for 30 days.

The workflow concurrency group reduces redundant overlapping work. Cancellation is not a freshness proof and is not used as publication authorization. This first workflow does not update a mutable current-result pointer.

The checkout and artifact-upload actions are pinned to reviewed full commit SHAs in the workflow. Re-review those pins when intentionally upgrading the actions.

Untrusted pull-request content must not receive secrets or write permissions. The workflow only checks out and inventories the merge revision; it does not execute repository build scripts or install repository-defined packages.

## 7. Storage policy

| Data | Storage |
|---|---|
| Committed source | GitHub Git object database |
| Runner checkout | Ephemeral hosted runner |
| Intermediate graph | Not persisted by this tranche |
| Source inventory and manifest | Compact Actions artifact |
| Full repository archive | Not created |
| External object storage | Not required |
| Actions cache | Not used as authority |

The inventory can be larger than a minimal manifest because it records one row per Git tree entry. It remains metadata and digests, not a second copy of source contents. Measure actual artifact size before changing the storage design.

## 8. Reproduction and tests

The tool uses only the Python standard library and the Git executable.

Capture:

~~~bash
python tools/ae32c_source_snapshot_manifest.py capture \
  --repository . \
  --output /tmp/source-snapshot-manifest.json \
  --expected-source-revision "$(git rev-parse HEAD)"
~~~

Postflight:

~~~bash
python tools/ae32c_source_snapshot_manifest.py verify \
  --repository . \
  --manifest /tmp/source-snapshot-manifest.json \
  --expected-source-revision "$(git rev-parse HEAD)"
~~~

Tests:

~~~bash
python -m unittest discover \
  -s tests/semantic_graph \
  -p 'test_ae32c_source_snapshot_manifest.py' \
  -v
~~~

For a pull-request event, capture also needs a GitHub event payload containing pull_request.base.sha and pull_request.head.sha; the Actions workflow supplies this automatically.

## 9. Failure semantics

The CLI exits with status 2 on source-identity, Git, encoding, worktree or manifest errors.

The postflight verifier writes a failure state into the manifest when a manifest was successfully loaded. It does not convert a failed check into a successful empty inventory.

Important failure reasons include:

- checked_out_commit_does_not_match_expected_source_revision;
- tree_entry_encoding_unsupported;
- worktree_not_clean_at_capture;
- source_identity_changed_after_capture;
- worktree_not_clean_at_postflight;
- manifest_schema_invalid.

A failed or missing manifest must be treated as an incomplete source-snapshot stage.

## 10. Next implementation stages

1. Bind graph schema, builder/frontend versions, graph digest and coverage manifest to source_snapshot_id.
2. Add rule-specific coverage and closed-world/negative-query contracts.
3. Add immutable run-result records and a separate freshness-guarded publication protocol.
4. Establish full-rebuild correctness and representative resource measurements.
5. Introduce incremental recomputation only for rule fragments with demonstrated dependency closure.
6. Add LLM, solver and remediation invocation envelopes bound to run identity.
7. Protect the trusted kernel and promotion path; qualify budgets, cancellation and late-result rejection.

No phase should claim completion solely because a workflow is green. Each acceptance statement must identify exact source SHA, workflow run, test evidence and assurance boundary.

## 11. Acceptance criteria

- [ ] Exact github.sha is checked against HEAD.
- [ ] Root tree and Git object format are recorded.
- [ ] Recursive tree inventory includes path, mode, object type and object ID.
- [ ] Blob bytes receive SHA-256 digests.
- [ ] Inventory digest is deterministic.
- [ ] Pull-request base/head/merge identities are distinct.
- [ ] Dirty worktree at capture is rejected.
- [ ] Tracked or untracked mutation at postflight is rejected.
- [ ] Manifest records failure rather than silently passing.
- [ ] Manifest artifact is written outside the checkout.
- [ ] Workflow permissions are read-only.
- [ ] No permanent source archive or external object store is introduced.
- [ ] Documentation and schema are committed with implementation.

**Current assurance statement:** this is a first source-identity and postflight-integrity implementation. It does not close G4 repository-wide atomicity, publication freshness, graph completeness or production approval.


## 12. Initial GitHub-hosted validation record

**Workflow run:** [45622987296](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45622987296)  
**Tested source revision:** f9b66a1bcecf73ff9c769f36bc4cb4959764f189  
**Workflow conclusion:** success  
**Artifact:** [ae32c-source-snapshot-45622987296-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45622987296/artifacts/15027620112)  
**Artifact ID:** 15027620112  
**Artifact size:** 142,662 bytes  
**Actions ZIP SHA-256:** 5367910c4d0073c34ad70b5844b3630346f053a99c91b3283e520a8a8284763f

The run executed eight standard-library unit tests. All passed:

- committed source/tree identity and blob digest;
- dirty-worktree rejection at capture;
- expected-commit mismatch rejection;
- manifest tamper detection;
- pull-request base/head/merge identity recording;
- tracked mutation rejection at postflight;
- unchanged-source postflight acceptance;
- untracked-file rejection at postflight.

The live GitHub push run captured and verified:

- commit: f9b66a1bcecf73ff9c769f36bc4cb4959764f189;
- root tree: c42346bfd27f741b0bfb20a67840f5e7b70d92a9;
- source inventory entries: 1,940;
- source inventory SHA-256: 84a1f772b3d64d16e785abe4290fd4edcfd78630f8adfdf363ff38f6b7135214;
- source snapshot ID: 68b73ef0a92212c5607a7ea917ff1c0eb6626a7f45ccf662f8f5a030e24ad436;
- postflight status: VERIFIED.

This validates the push-event path and the tested manifest contract for that exact source revision. It does not yet constitute an end-to-end pull-request workflow execution, JSON Schema validator execution, atomic repository-wide snapshot, stale-publication test or production approval. The artifact digest is GitHub's reported ZIP digest; this record does not claim an independently signed attestation.

# AE-32C Phase 5.1 — Trusted Publisher Boundary

**Status:** Design contract recorded; no privileged publisher workflow is active.  
**Branch:** `stage1/section-uuids`  
**Production approval:** false  
**PR execution:** deferred until the user confirms the branch has been merged or explicitly requests PR validation.

## 1. Purpose and current boundary

The source/graph audit workflow is intentionally unprivileged:

- `contents: read` only.
- It checks out the exact event revision with checkout credentials not persisted.
- It executes repository-controlled Python.
- It accepts pull-request events as well as branch pushes.
- It uploads source and graph manifests as an artifact.

That workflow must remain unprivileged. A write-capable token must not be added to this job. The artifact is untrusted input, including when its JSON is syntactically valid and its self-digests match.

The durable adapter in `audit_engine/semantic_audit/ae32c/github_publication.py` is a storage mechanism, not a trust decision. Its fake-transport tests do not establish live GitHub authorization, branch protection, or artifact authenticity.

## 2. Required two-workflow topology

### Workflow A — audit producer (existing)

Responsibilities:

1. Check out and audit the exact event revision.
2. Produce source and graph manifests.
3. Run deterministic tests and postflight source identity checks.
4. Upload the evidence artifact.
5. Never receive a write-capable credential.

The existing workflow remains `permissions: contents: read`.

### Workflow B — trusted publisher (future)

The publisher must be defined on the repository's default branch before `workflow_run` can activate it. It must run from the trusted default-branch workflow definition and trusted publisher code, not from the audited commit.

The publisher must:

1. Trigger only after the exact, allowlisted audit workflow completes.
2. Accept only a successful `push` run on the protected default branch.
3. Require `head_repository.full_name == github.repository`.
4. Require `head_branch == main` (or the explicitly configured protected default branch).
5. Reject pull-request, fork, dispatch, schedule, and any other event for current publication. These may be retained as history by a separately authorized process, but must not advance current.
6. Verify the upstream workflow ID, run ID, run attempt, repository, event, branch, and head SHA using the GitHub event/API metadata—not values copied from the artifact.
7. Download only the expected artifact belonging to that exact upstream run. Verify its artifact ID/name and reject missing, expired, duplicate, or unexpected files.
8. Treat every artifact byte as untrusted data. Parse and validate; never execute, import, source, or invoke anything from the artifact.
9. Check out only the publisher workflow's trusted revision. Never check out or execute the upstream `head_sha` in the privileged job.
10. Require an environment approval gate before obtaining the publication credential.
11. Resolve the live authorized source branch ref immediately before publication. The GitHub CAS adapter must resolve it again for its own eligibility check and readers must continue to re-check it.
12. Publish using the durable ref-CAS backend and preserve all non-current outcomes as history.

The `workflow_run` trigger is privileged. Its security depends on the publisher workflow being present on the default branch, strict event/run validation, and never executing upstream-controlled content.

## 3. Credential and ref protection

The publisher is the only component that receives a write-capable credential.

Preferred deployment:

- A GitHub App installation token restricted to this repository and the minimum required permission (`contents: write`).
- A repository ruleset targeting only `ae32c-publication-state`, configured so only the designated publisher identity can update that ref.
- A required-reviewer GitHub Actions environment such as `ae32c-publication`.
- No credential in the producer workflow, artifacts, repository files, logs, or model context.

The GitHub App permission alone is repository-scoped, not ref-scoped. The publication-branch ruleset is therefore a required control, not an optional hardening measure. If the ruleset cannot be configured, the publisher must not be activated with a broadly write-capable credential.

Do not solve this by changing the existing producer workflow to `contents: write`.

## 4. Artifact validation contract

The publisher must validate both manifests independently and then validate their cross-bindings.

### Source manifest

Require:

- Exact schema `ae32c/source-snapshot-manifest/v1`.
- `status == VERIFIED` and `verification.status == VERIFIED`.
- Valid manifest SHA-256 over canonical JSON excluding `manifest_sha256`.
- Valid source inventory count and digest.
- Valid source snapshot identity and root tree identity.
- `verification.source_snapshot_id_at_verification` equals the captured source snapshot ID.
- `verification.source_inventory_sha256_at_verification` equals the inventory digest.
- `verification.worktree_clean_at_verification == true`.
- Repository, commit SHA, event name, ref, run ID, and run attempt match the independently obtained upstream run metadata.
- For current publication, event is `push` to the protected default branch.

### Graph manifest

Require:

- Exact schema `ae32c/graph-snapshot-manifest/v1`.
- Valid manifest digest, graph identity digest, coverage digest, and finding-ledger digest.
- Existing graph-manifest verifier succeeds.
- Graph source snapshot ID equals the verified source manifest's snapshot ID.
- Graph repository and commit SHA equal the source manifest's repository and commit SHA.
- Finding ledger and rule-registry digest references agree.
- No unaccounted source units for a current result.
- Coverage status is `COMPLETE_WITH_DECLARED_EXCLUSIONS` for a current result. Otherwise classify the run as `INCOMPLETE` and retain it as history only.

A valid digest proves internal consistency against the supplied bytes. It does not prove that repository-controlled producer code honestly computed the graph or that a finding is semantically entailed. The publisher must not upgrade structural provenance into semantic proof.

### Run record

The immutable publication record must bind:

- Repository and exact source revision.
- Source and graph snapshot IDs.
- Rule registry and finding ledger digests.
- A canonical configuration digest covering the producer workflow identity/revision, graph builder/projection contract, rule registry, and explicit publication-policy version.
- Upstream workflow ID, run ID, run attempt, and generation.
- Terminal outcome.

The publisher's configuration digest must be derived from independently checked run metadata and validated manifest fields. Do not accept a configuration digest supplied without verification by the artifact.

## 5. Current-result eligibility

A run may advance `current` only if all of the following hold:

- Exact allowlisted workflow ID.
- Same repository; no fork.
- `push` event to the protected default branch.
- Upstream workflow conclusion is `success`.
- Upstream source SHA matches the verified source manifest commit.
- The source ref still resolves to that SHA at authorization time.
- Both manifests and all cross-bindings validate.
- Graph coverage is complete with declared exclusions and has zero unaccounted units.
- Generation is strictly newer than the last published generation.
- Publication-ref compare-and-swap succeeds.
- A subsequent live-ref check still matches the authorized source SHA.

Any failed, cancelled, incomplete, superseded, non-authorized, or stale run is not current. Preserve it as history only when its metadata and artifact can be safely validated; otherwise reject it without publication.

## 6. Required tests before activation

### Artifact/parser tests

- Wrong schema, missing fields, duplicate JSON keys, invalid UTF-8, NaN/Infinity, oversized files.
- Digest mismatch at each manifest, inventory, coverage, identity, and ledger layer.
- Duplicate source paths, invalid counts, malformed commit IDs.
- Source/graph cross-binding mismatch.
- Wrong repository, event, ref, run ID, run attempt, workflow ID, branch, or head SHA.
- Missing, duplicate, unexpected, expired, or mismatched artifact.
- Incomplete coverage and nonzero unaccounted units.
- Malicious artifact filenames and archive path traversal; artifact contents are never executed.

### Publisher integration tests

- Fork PR and same-repository PR cannot advance current.
- Push to an unprotected feature branch cannot advance current.
- Successful protected-default-branch push can advance current only after environment approval.
- Superseded source cannot become current.
- Branch movement between pre-check and CAS cannot remain current.
- Concurrent publisher attempts serialize through ref CAS.
- Credential is unavailable to the producer job and unavailable before environment approval.
- Publisher code comes from the trusted default branch, not the upstream head SHA.
- Current pointer revalidation fails closed if the source branch later moves.
- History retention and compaction preserve integrity and auditability.

## 7. Activation blockers

Do not activate a write-capable publisher until all are true:

1. The trusted publisher workflow and validator are reviewed and present on the default branch.
2. The default branch's protection/required-review policy is verified.
3. The publication-ref ruleset is configured and verified.
4. The protected environment and required reviewers are configured.
5. The GitHub App/credential is installed with minimum permissions.
6. Artifact validation and policy tests pass.
7. Live ref-CAS integration is tested in a controlled repository/ref.
8. Retention/compaction policy for the append-only state document is defined.
9. The user explicitly authorizes activation.

## 8. Current disposition

The existing producer workflow remains read-only and is not wired to the durable publisher. The adapter remains fake-transport tested only. No publication ref has been created by this project, no live write credential has been used, no trusted publisher is active, and no production result pointer exists.

This document defines the next implementation and acceptance boundary; it does not claim that the publisher is operational.


## 9. Implemented validator status (2026-11-25)

The following controls are now implemented on `stage1/section-uuids` in
`audit_engine/semantic_audit/ae32c/trusted_artifact.py`:

- Canonical JSON digest verification, duplicate-key rejection, non-finite-number rejection, strict UTF-8 parsing, and bounded manifest sizes.
- ZIP archive parsing that accepts exactly the two expected root-level JSON members, rejects duplicate/unexpected members, traversal-like names, links/non-regular members, encryption, unsupported compression, excessive member/archive sizes, and excessive compression ratios.
- Source manifest identity, inventory digest/count/path uniqueness/order, Git object ID/mode/type/materialization metadata, checkout commit/tree identity, clean-worktree state, and postflight identity checks.
- Independent event/repository/ref/default-branch/head-SHA/run-ID/run-attempt checks.
- Exact producer workflow allowlist: workflow ID `430355742` and path `.github/workflows/ae32c_source_snapshot_manifest.yml`.
- Graph manifest verifier, source snapshot/commit/tree cross-bindings, graph authority flags, and nonnegative node/edge counts.
- Per-path graph coverage reconciliation against the exact source inventory Git object ID and content digest; status/reason validation; aggregate/status-count reconciliation; unaccounted-path reconciliation; extractor issue/count consistency.
- Current eligibility only for `COMPLETE_WITH_DECLARED_EXCLUSIONS` coverage with zero unaccounted units and no declared extractor issues; otherwise the result is history-only as `INCOMPLETE`.
- Configuration digest derived from independently supplied workflow metadata and validated graph builder/rule-registry identity.

The producer workflow remains `contents: read`; the validator is not wired to any privileged workflow or credential.

### CI evidence

The validator and producer pipeline passed:

- Workflow run: [45666618999](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45666618999)
- Tested commit: `28a1a4e6ff31ee0e94052f248808ecd8eee5e262`
- Job: `139391006971`
- Trusted-artifact tests: 15 passed.
- Other AE-32C test groups in the same job: source snapshot, graph snapshot, rule contracts, local publication state machine, and GitHub CAS adapter; all steps succeeded.
- Source inventory: 1,955 entries.
- Graph coverage: 1,887 represented, 68 declared exclusions, 0 unaccounted.
- Graph snapshot ID: `bb44d57ac4d20137bf55a26da7119346c09506a6c1f5212b8cfdeefd8bd102c4`.
- Artifact ID: `15048755034`, 292,815 bytes; uploaded ZIP SHA-256 `fb8560a10a2bb9b894f105549713c46080ab507286cb08b9b890aadbcad1a202`.

These are CI and internal-consistency results only. The tests use constructed fixtures and fake GitHub transports; they do not establish artifact authenticity, semantic correctness, live ref-CAS behavior, GitHub branch/ruleset enforcement, or production authorization.

### Remaining validator and publisher work

- The archive parser is unit-tested but is not yet called by a publisher entry point.
- The validator accepts independently retrieved metadata as an argument; the future workflow must retrieve it directly from GitHub API endpoints and enforce the allowlist before downloading or processing artifacts.
- The source manifest currently has no JSON Schema validation step in the producer workflow. Add strict schema validation in the trusted publisher, using trusted schema files from its own checked-out revision.
- The GitHub CAS adapter currently stores an unbounded append-only JSON history. Define compaction/retention before operational use.
- No live App token, publication ref, environment approval, ruleset, or protected-default-branch guarantee has been exercised.

## 10. Trusted publisher implementation scaffold (2026-11-25)

The repository now contains:

- `tools/ae32c_trusted_publisher.py`: read-only preparation phase retrieves the upstream run and repository metadata directly from GitHub, checks the exact producer workflow identity, selects the unique artifact named for the upstream run ID and attempt, verifies the GitHub-provided artifact SHA-256, downloads it with a size cap, validates the ZIP and trusted local schemas, and writes an immutable run record to the runner temporary directory.
- A separate publish phase requires `AE32C_PUBLICATION_TOKEN` and delegates to `GitHubRefCASStore`. The workflow mints this token only after preparation has completed.
- Artifact download redirects are handled without forwarding the GitHub API bearer token to a different origin.
- `tests/semantic_graph/test_ae32c_trusted_publisher.py` covers API metadata mapping and exact, unique, unexpired artifact selection.
- `.github/workflows/ae32c_trusted_publisher.yml` uses `workflow_run`, checks out the trusted default-branch revision, validates before token creation, and requests a repository-scoped GitHub App token with only `contents:write`.

**Activation state:** the workflow is deliberately disabled unless repository variable `AE32C_TRUSTED_PUBLISHER_ENABLED` is exactly `true`. It has not been activated. It is only present on `stage1/section-uuids`; it cannot receive `workflow_run` events until it is merged into the default branch. The repository's default-branch protection status remains unverified, no publication-ref ruleset or required-reviewer environment has been confirmed, and no App credentials have been configured or used.

The publisher scaffold is not yet live-verified. CI currently validates the pure metadata/artifact-selection functions and imports the orchestration module. A live GitHub API download, redirect behavior against GitHub's artifact service, App-token issuance, ruleset enforcement, and publication-ref CAS remain untested. The publisher must remain disabled until the activation blockers in Section 7 are cleared and the user explicitly authorizes activation.

### Publisher orchestration hardening and CI result

The orchestration layer now additionally:

- Requires the GitHub run object's repository identity to equal the target repository.
- Requires the artifact's embedded workflow-run ID and head SHA to equal the exact upstream run.
- Rejects duplicate artifact names, expired artifacts, missing artifact digests, and mismatched artifact metadata.
- Compares downloaded ZIP bytes against the SHA-256 digest returned by GitHub's artifact API.
- Handles the GitHub artifact redirect without forwarding the GitHub API bearer token to a different origin.
- Prefilters the workflow to successful same-repository pushes to the default branch, while repeating all authorization checks in the Python validator.

CI run [45669000822](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45669000822) passed on commit `f573aade69b348d672bec1d1bbb111627a43ef01`. The publisher orchestration suite passed 9 tests; the trusted artifact suite passed 18 tests; all 19 workflow steps succeeded. The producer artifact for this run was ID `15049071901`, 293,271 bytes, with GitHub-reported SHA-256 `86fa9a11578016f6cccb28d3f048a668a2dac012bea39f17e1024b770a169f2d`. The source inventory contained 1,958 entries; graph coverage represented 1,890, declared 68 exclusions, and had zero unaccounted units.

These tests do not execute the publisher workflow, obtain an App token, download a live upstream artifact through the workflow-run context, or write the publication ref. The publisher remains gated and unactivated.

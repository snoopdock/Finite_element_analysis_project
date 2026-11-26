# AE-32C Phase 2 — Graph Snapshot Identity and Coverage

**Status:** Implemented on `stage1/section-uuids`; pull-request execution deliberately deferred  
**Scope:** Bind a derived semantic graph projection to the verified Git source snapshot and account for source coverage  
**Production approval:** Not granted

## 1. Purpose

Phase 1 established `source_snapshot_id` from the exact Git commit, root tree, inventory and blob digests. Phase 2 adds a separate graph identity. It does not change the authority hierarchy:

- Git commit/tree and source inventory remain canonical repository facts.
- AE-32B builds a derived semantic graph from its declared evidence scope.
- The graph snapshot records the builder/projection contract, graph content digest and coverage.
- Findings and later analyses must bind to both source and graph identities.
- A graph is not complete merely because graph construction returned successfully.

## 2. Graph identity contract

The graph snapshot binds:

1. `source_snapshot_id`, source commit and root tree;
2. graph schema version;
3. AE-32B graph builder and projection contract versions;
4. Python runtime version;
5. a deterministic SHA-256 digest of canonicalized graph nodes and edges;
6. a deterministic SHA-256 digest of the coverage manifest.

Nodes are sorted by semantic ID and canonical representation. Edges are sorted by canonical JSON while preserving parallel edges. Duplicate node IDs, malformed relations and dangling edge endpoints fail closed.

The graph itself is not copied into the retained artifact. Only node/edge counts and its content digest are retained. This avoids making a second persistent repository or graph archive. Rebuilding the graph from the same source and contract can be checked against the recorded digest.

## 3. Source-to-graph coverage

The coverage manifest accounts for every Git tree entry and distinguishes:

- `represented`: an evidence-scope source unit has a graph file node whose source digest matches the evidence inventory;
- `excluded_sensitive`: omitted under the sensitive-path policy;
- `excluded_symlink`: symlink not followed;
- `excluded_by_evidence_inventory`: the evidence inventory explicitly excluded the source unit;
- `outside_declared_source_scope`: outside the AE-32A source suffix/directory policy;
- `unaccounted`: an included source unit has no graph file node.

The manifest also records Python AST, workflow static-scan, structured-record and module-identity coverage. Parse, scope, workflow, structured-record, module-identity or source-to-graph correspondence problems make graph coverage incomplete.

`COMPLETE_WITH_DECLARED_EXCLUSIONS` means every Git entry has an accounted disposition and the current extractor reported no known issue within its declared scope. It does not mean every repository byte or every semantic relationship has been modeled. Exclusions remain visible in the manifest.

## 4. Negative findings and closed-world claims

Negative findings are **denied by default**, even when this graph-coverage status is complete. A future rule must provide a query-specific closed-world contract identifying:

- the relevant source-unit scope;
- the extractor and relation types required;
- completeness conditions for those extractors;
- exclusions and unresolved units that could affect the query;
- the exact source and graph snapshot identities.

A global graph-complete flag is not sufficient proof that a particular negative claim is valid. Weighted scores or graph reachability alone do not establish absence.

## 5. Workflow and deferred pull-request execution

The existing AE-32C workflow is extended to build the graph manifest after source snapshot verification. It runs on pushes to `stage1/section-uuids`, supports manual dispatch, and is configured for pull requests targeting either `stage1/section-uuids` or `main`.

The `main` push trigger is also enabled so the workflow runs after this branch is integrated. The `main` pull-request target is configured for subsequent PR validation once the workflow is present on the base branch. No pull request was opened or dispatched as part of this tranche. The pull-request event path is not yet end-to-end validated. In particular, its merge-revision source identity and base/head event fields remain pending a real PR run after the branch is ready to merge.

The workflow retains compact source and graph manifests, not the full repository or graph serialization. It installs only the PyYAML runtime dependency required by the existing static audit implementation and uses the reference graph backend; no native backend performance selection is performed.

## 6. Validation

The Phase 2 unit suite covers:

- deterministic graph identity under node ordering changes;
- binding to source snapshot identity;
- incomplete coverage for unaccounted source units;
- default denial of negative findings;
- source-to-graph digest mismatch rejection;
- dangling-edge rejection;
- source-manifest tamper rejection;
- extractor issue propagation to incomplete coverage.

A successful push workflow run validates the branch push path only. It does not validate the pull-request event path, establish atomic filesystem snapshot semantics, prove semantic completeness, or grant production approval.

## 7. Push-path validation record

**Workflow run:** [45628899256](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45628899256)
**Tested source revision:** `c7ce3ebb1f970609254dc540807a68688c1cee0a`
**Workflow conclusion:** success
**Job:** Capture source and derived graph identity
**Artifact:** [ae32c-source-graph-snapshot-45628899256-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45628899256/artifacts/15027934823)
**Artifact ID:** `15027934823`
**Artifact size:** 285,526 bytes
**GitHub-reported ZIP SHA-256:** `9cd21e62387ea5d3082ad7f61f97ebeb20377d9c3574d3c9f0b15238b78eea2c`
**Independently recomputed ZIP SHA-256:** same value

The run passed eight source-snapshot tests and ten graph-snapshot tests. The exact source revision was captured and postflight-verified both before and after graph projection.

Recorded identities and counts:

- source snapshot: `8d74d185a442312503a78799b450bbbbd7ee5e64ea498bc05e1b63d31ceae432`;
- root tree: `8cde1ea64b1d91efc7034ed838b4d33067176e9f`;
- source inventory: 1,944 Git tree entries, SHA-256 `b7fea2c5c9af8a4338cdd9612197b9a5b6d5cb02c1a409c926827deacc299778`;
- graph snapshot: `abb05b39256689aad1c20cf1f25ce3bcabac8d42bda72e91d7f5344a9541900b`;
- graph content SHA-256: `e2719cb1251e7e73f8f6003eac58f7f724d25de375783b34a4a4efe1e85b4612`;
- graph size: 11,254 nodes and 40,042 edges;
- coverage: 1,876 represented source units, 68 outside the declared evidence-source scope, zero unaccounted units;
- Python AST: 1,106 candidates, 1,106 parsed, zero parse failures;
- workflow static scan, structured-record ingestion and module identity: zero reported issues.

The resulting coverage state was `COMPLETE_WITH_DECLARED_EXCLUSIONS`. This is completeness within the recorded source/extractor policy, not proof that every semantic relationship is represented. Negative findings remain prohibited by default. The run was a push-event validation only; it does not validate the pull-request event path or authorize production use.

## 8. Known limits and next work

- The current coverage contract is file/source-unit oriented; it does not prove completeness of every possible semantic relation.
- Git submodule contents and external Git LFS payloads remain outside the Phase 1 source inventory boundary.
- No signed attestation or independent runner attestation is produced.
- The graph content digest is a reproducibility identity, not a proof that the extractor is correct.
- Rule-specific closed-world query contracts are not implemented.
- Finding-to-source/graph/rule binding is the next logical stage after this contract is reviewed.
- Incremental recomputation, persistent graph storage, LLM orchestration, solver orchestration, remediation and automatic merge remain out of scope.
- `production_approval=false`.

## 9. Files

- `tools/ae32c_graph_snapshot.py`
- `tests/semantic_graph/test_ae32c_graph_snapshot.py`
- `docs/audit-engine/schemas/ae32c-graph-snapshot-manifest-v1.schema.json`
- `.github/workflows/ae32c_source_snapshot_manifest.yml`


## 10. Generated Graphify analysis artifacts — source-scope boundary

The tracked directory `branch-graphify-results/` contains generated Graphify reports,
interactive graph exports, run logs and derived JSON summaries. These are analysis
artifacts, not repository source inputs for the AE-32A/AE-32B source-evidence graph.

The source-evidence scanner therefore excludes the exact directory prefix
`branch-graphify-results/` from its semantic source inventory. This is a directory-
scoped policy, not a filename-wide exclusion: JSON, Markdown or Python files elsewhere
remain subject to the normal source-suffix and ingestion rules.

This exclusion does **not** remove the files from the canonical Git source snapshot.
The Phase 1 Git inventory continues to enumerate and hash every tracked Git blob,
including Graphify outputs. The graph coverage manifest accounts for these entries
as `outside_declared_source_scope`, with the declared scope policy recorded in the
audit report. They are not silently dropped from repository identity or source
inventory accounting.

Graphify results remain available as separately retained analysis evidence. Their
presence or digest does not establish that a graph backend is operational, that
an adapter is invoked, or that a finding is semantically supported. Those questions
require branch-specific operational evidence and explicit validation.

The exclusion is deliberately limited to the generated results directory. It does
not exclude the Graphify implementation under `tools/branch-graphify/`, its workflow,
or its requirements file from source analysis.

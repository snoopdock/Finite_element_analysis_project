# AE-32C M7.5.12 — Source and Extractor Inventory Reconciliation

**Status:** Implemented and exact-source CI-validated; 127 M7.5 regression tests passed (run [45908133784](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45908133784))  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.11 — Independent Coverage Dossier Verification and Replay  
**Authority:** deterministic inventory reconciliation relative to a verified source manifest and a versioned built-in extractor-candidate registry only

## 1. Problem addressed

M7.5.9 derives obligation IDs from caller-selected rule contracts. M7.5.10 reconciles persisted knowledge gaps to those obligations. M7.5.11 independently verifies dossier semantics and replays the evaluation when source-ledger tokens match.

Those milestones do not enumerate every tracked source unit or derive extractor candidates for those units. A rule-level requirement such as `python_ast` or `source_manifest` therefore does not itself prove which files were eligible for that extractor, which files were outside declared scope, or which files had no registered extractor.

## 2. New module and APIs

Module: `audit_engine/semantic_audit/epistemic/source_inventory.py`

- `SourceExtractorInventoryError`
- `extractor_candidate_registry()`
- `build_source_extractor_inventory(source_manifest, scope_exclusions=...)`
- `verify_source_extractor_inventory(source_manifest, inventory)`

The builder accepts only a postflight-verified AE-32C source snapshot manifest. It validates the manifest digest, source inventory digest/count, stable path ordering, unique safe relative paths, supported Git object types/modes and content digests.

The built-in registry is versioned and digest-sealed. Initial candidate families:

- `python_ast`: tracked `.py` blob entries.
- `workflow_static_scan`: tracked `.yml` and `.yaml` blob entries.

This is a candidate registry, not an extractor runtime registry. It does not claim that the extractor implementation ran successfully.

## 3. Reconciliation semantics

Every source-manifest entry is retained and classified:

- `EXTRACTOR_CANDIDATE`: one or more registered extractors match the path.
- `NO_REGISTERED_EXTRACTOR`: a blob source unit has no matching extractor; it is listed explicitly.
- `GITLINK_SUBMODULE`: a Git submodule pointer is separately identified and is not treated as a blob.
- `DECLARED_EXCLUDED`: an explicit path/reason exclusion is retained in the source-unit record and any matching candidate record.

Every extractor candidate binds the source path, source content SHA-256, extractor ID/version, candidate kind and status. Candidate IDs are deterministic. Candidates are marked `CANDIDATE_NOT_EXECUTED` unless explicitly excluded.

The verifier checks the inventory's own digest and then independently rebuilds the expected inventory from the verified source manifest, built-in registry and recorded exclusions. A caller cannot make a semantically incomplete inventory valid merely by recomputing its digest.

## 4. Structural and behavioral tests

The dedicated suite `tests/semantic_graph/test_m7512_source_inventory.py` covers:

- Registry version and digest.
- Full source-entry classification.
- Candidate derivation from suffix contracts.
- Explicit unsupported-source and Gitlink partitions.
- Non-execution semantics.
- Explicit exclusion preservation and unknown-exclusion rejection.
- Postflight verification requirement.
- Source-manifest and inventory digest checks.
- Duplicate and unsafe path rejection.
- Rehashed semantic tampering rejection.
- Independent verification of a valid inventory.

## 5. Validation

Exact-source workflow: [45908133784](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45908133784)

- Validated source revision: `6944c0edeb5343edf6cb267121d704e700c2c68c`
- Runtime: Ubuntu 24.04, Python 3.11
- Dedicated M7.5.12 tests: 12 passed
- Complete M7.5 regression: 127 passed
- Epistemic package compilation: passed
- Job ID: `140209754323`
- Artifact: `m7-5-12-source-inventory-45908133784-1`
- Artifact ID: `15158666628`
- Artifact ZIP SHA-256: `6740799eb20885afc2757a6721326b529498c6646c5294f10ade7fa510e0aa26`

The workflow checks out the exact triggering SHA. The dedicated suite and the complete M7.5 regression both passed. A documentation-only validation-record commit follows; the implementation source is unchanged.

## 6. Explicit limitations

M7.5.12 does **not** establish:

1. That the Git source manifest itself represents every relevant external, generated, ignored, submodule or LFS payload.
2. That the built-in extractor-candidate registry includes every useful or applicable extractor.
3. That any candidate extractor was executed, completed, or produced correct results.
4. That a source file's suffix accurately describes its language or semantics.
5. That source units or extractor candidates are semantically relevant to every selected rule.
6. Atomicity across repository, graph, assurance, epistemic and dossier stores.
7. Proposition truth, universal evidence completeness, ALLOW/DENY, audit-gate authorization or production approval.

The result is complete only relative to the verified source-manifest entries and the exact built-in registry version/digest recorded in the inventory. Unsupported source units remain visible rather than silently disappearing.

## 7. Validation commands

```bash
python -m unittest discover -s tests/semantic_graph -p 'test_m7512_source_inventory.py' -v
python -m unittest discover -s tests/semantic_graph -p 'test_m75*.py' -v
```

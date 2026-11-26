# AE-32C M7.5.13 — Extractor Execution Evidence and Result Reconciliation

**Status:** Implemented and exact-source CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.12 — Source and Extractor Inventory Reconciliation  
**Authority:** deterministic execution evidence over source bytes bound to a verified source snapshot; no audit-decision authority

## 1. Purpose

M7.5.12 inventories candidates but deliberately does not claim they were investigated. M7.5.13 records exactly one execution outcome for every candidate. Outcome reconciliation is distinct from successful extraction.

## 2. APIs and CLI

Module: `audit_engine/semantic_audit/epistemic/extractor_execution.py`

- `ExtractorExecutionError`
- `extractor_executor_registry()`
- `build_extractor_execution_report(...)`
- `verify_extractor_execution_report(...)`

CLI: `tools/ae32c_extractor_execution.py` — `execute` builds inventory and report JSON; `verify` independently re-executes and compares the complete canonical report.

The report binds the source snapshot/manifest, candidate inventory, executor registry, limits, source content digests, extractor versions, outcomes and result digests.

## 3. Actual extractor contracts

- `python_ast`: the existing `ASTExtractor`, extended to parse the exact hashed byte sequence. It extracts imports and direct call-site symbols. Source is parsed, never imported or executed.
- `workflow_static_scan`: a conservative line-oriented scanner for selected YAML keys. It is not a YAML parser and does not validate GitHub Actions semantics.

The executor registry is separately versioned; the M7.5.12 candidate registry and historical inventory digests remain unchanged.

## 4. Outcome model

Every candidate receives one of `EXECUTED`, `FAILED`, `UNSUPPORTED_INPUT`, `UNSUPPORTED_EXECUTOR`, `RESOURCE_LIMIT`, or `SKIPPED_EXPLICIT_EXCLUSION`. Digest mismatch is failure; symlinks are not followed; byte and AST-node limits are explicit.

`RECONCILED` means every candidate has exactly one outcome, not that every candidate succeeded. Execution status is separately `ALL_EXECUTED`, `PARTIAL`, `NONE_EXECUTED` or `NO_CANDIDATES`.

## 5. Verification and tests

The verifier re-derives the inventory, re-executes each candidate against the same checkout and compares the full report. Tests cover real extraction, source non-execution, lexical-only YAML observations, digest mismatch, syntax failure, resource limits, exclusions, symlinks, replay, rehashed tampering, missing outcomes and malformed inventory.

The workflow preserves the original postflight-verified source manifest for report replay. A separate copy is used for the post-extraction source verification because the verification tool updates the manifest's verification timestamp and digest. The two manifests are required to retain the same source snapshot ID and source-inventory digest.

## 6. Exact-source CI validation

Workflow: [45909845857](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45909845857)

- Validated source revision: `f56f4b494fb1245b4bda85bce30f4b79b78a2ddb`
- Runtime: Ubuntu 24.04, Python 3.11
- Package compilation: passed
- Dedicated M7.5.13 tests: 14 passed
- Complete M7.5 regression: 141 passed
- Candidate count: 1,382
- Outcome count: 1,382
- Outcomes: 1,382 `EXECUTED`
- Execution status: `ALL_EXECUTED`
- Independent replay: passed; exact report match
- Source identity postflight: passed
- Job ID: `140215275993`
- Artifact: `m7-5-13-extractor-execution-45909845857-1`
- Artifact ID: `15159717182`
- Artifact ZIP SHA-256: `341c65ec4e443ac5b219291238fce3559f670805a9df0f7757135de98627c799`
- Execution report SHA-256: `28683200b202ce7b746397a64436cd9761e827c6d1b8d60509e3e1b6e0fc5aec`

The report records 1,382 candidates and 1,382 outcomes. The verifier independently re-executed the candidate set and confirmed the complete report digest and semantic content.

## 7. Limitations

M7.5.13 does not establish:

1. Universal source or extractor inventory exhaustiveness.
2. YAML semantic validity, GitHub Actions runtime behavior or workflow safety.
3. Full Python semantic understanding; the AST extractor records imports and direct calls only.
4. Extractor correctness beyond the specified tests.
5. Isolation against every parser denial-of-service input; byte/node limits are not a complete sandbox.
6. Completeness of generated, ignored, external, LFS or submodule payloads absent from the manifest.
7. Atomicity across source, graph, assurance, epistemic and dossier stores.
8. Proposition truth, universal evidence completeness, ALLOW/DENY, audit-gate authorization or production approval.

The report is a per-run artifact, not yet a durable append-only cross-run ledger and not yet attached to the M7.5.10 coverage dossier. Those integrations require separate contracts.

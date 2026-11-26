# AE-32C M7.5.13 — Extractor Execution Evidence and Result Reconciliation

**Status:** Implemented; exact-source CI validation pending  
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

`RECONCILED` means every candidate has exactly one outcome, not that every candidate succeeded. Execution status is separately `ALL_EXECUTED`, `PARTIAL`, `NONE_EXECUTED`, or `NO_CANDIDATES`.

## 5. Verification and tests

The verifier re-derives the inventory, re-executes each candidate against the same checkout and compares the full report. Tests cover real extraction, source non-execution, lexical-only YAML observations, digest mismatch, syntax failure, resource limits, exclusions, symlinks, replay, rehashed tampering, missing outcomes and malformed inventory.

## 6. Limitations

No universal inventory exhaustiveness; no YAML semantic validation; no full Python semantic analysis; no complete parser sandbox; no assurance for generated/ignored/external/LFS/submodule payloads absent from the manifest; no cross-store atomicity; no proposition truth, ALLOW/DENY, gate authorization or production approval.

The report is a per-run artifact, not yet a durable append-only cross-run ledger and not yet attached to the M7.5.10 coverage dossier.

## 7. Validation

Pending exact-source CI:

```bash
python -m unittest discover -s tests/semantic_graph -p 'test_m7513_extractor_execution.py' -v
python -m unittest discover -s tests/semantic_graph -p 'test_m75*.py' -v
```

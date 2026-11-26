# AE-32C M7.5.15 — Typed Evidence Observations and Rule-Obligation Binding

**Status:** Implemented; exact-source CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.14 — Execution-to-Obligation Reconciliation  
**Authority:** source-bound structural observations only; no semantic acceptance or audit-decision authority

## 1. Purpose

M7.5.14 established that extractor candidates executed and were reconciled to the selected rule-obligation universe. It deliberately did not treat extractor output as typed semantic evidence.

M7.5.15 introduces a typed observation envelope and binds observations to the evidence-kind obligations derived from the versioned rule contracts. The output is an auditable observation bundle, not an assertion that a rule's proposition is true or that its evidence requirement is satisfied.

## 2. Implemented evidence producers

Only three narrowly checkable producer kinds are enabled:

| Evidence kind | Producer | What is established | What is not established |
|---|---|---|---|
| `graph_import` | `python_ast_import_root_v1` | A parsed import statement names a module root in the explicit graph-library allowlist | Actual runtime use, service reachability, graph computation, or absence from an LLM path |
| `python_syntax_error` | `python_ast_parse_failure_v1` | The pinned source failed the registered Python AST parse operation with a recorded syntax diagnostic | Whether the source is otherwise semantically defective |
| `scope_exclusion` | `source_inventory_exclusion_v1` | The verified inventory explicitly records a path and exclusion reason | Scope completeness or adequacy of the exclusion |

Every emitted record has source snapshot, path and content digest, producer/extractor identity, candidate/outcome identity where applicable, source line and line digest where applicable, rule-obligation binding, canonical identity, and explicit limitations.

## 3. Unsupported evidence kinds

Evidence kinds such as `external_model_response_intake`, `llm_transport_call`, `model_tool_protocol_indicator`, `tool_dispatch_indicator`, `workflow_command`, and `fixed_context_allowlist` are not inferred from generic AST symbols or lexical YAML keys. They remain `NO_AUTOMATIC_VALIDATOR` until a domain-specific producer and validator are implemented.

A missing structural match is separately reported as `NO_MATCHING_STRUCTURAL_OBSERVATION`. Neither state is a negative finding.

## 4. APIs

Module: `audit_engine/semantic_audit/epistemic/typed_evidence.py`

- `TypedEvidenceError`
- `derive_typed_evidence_observations(...)`
- `verify_typed_evidence_observation_bundle(...)`
- `TypedEvidenceObservationStore`
- `build_and_persist_typed_evidence_observations(...)`

The persistent store is a separate append-only SQLite hash-chain ledger with idempotent bundle identity, bounded records, integrity verification, history, and lookup. The builder verifies the M7.5.8 rule-derived manifest, M7.5.12 inventory, and M7.5.13 execution report before persistence.

## 5. Validation tests

Structural and behavioral tests cover:
- Exact source-bound graph-import observations.
- Syntax-error observations bound to failed AST outcomes.
- Unsupported semantic evidence remaining unresolved.
- Full deterministic replay and source-drift rejection.
- Bundle digest tampering.
- Append-only persistence, idempotence, and restart recovery.

## 7. Exact-source CI validation

Workflow: [45911493746](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45911493746)

- Validated source revision: `7b2abccc058842c75511b1a0f40135f2351e6c7b`
- Runtime: Ubuntu 24.04, Python 3.11
- Epistemic package compilation: passed
- Dedicated M7.5.15 tests: 8 passed
- Complete M7.5 regression: 156 passed
- Job ID: `140220687772`
- Final job conclusion: success

An earlier run caught an invalid literal escape in the package export list before tests could execute. The export formatting was corrected; the successful run above compiled the package and passed both test layers.

## 8. Limitations

M7.5.15 does not:
1. Treat structural observations as accepted semantic evidence.
2. Create `EvidenceAssertion` records or mutate the epistemic store.
3. Resolve M7.5.10 coverage gaps or upgrade dossier status.
4. Prove that imported graph libraries are invoked or used correctly.
5. Prove negative/absence claims; existing rule contracts without a validated closed-world contract remain subject to ABSTAIN.
6. Implement semantic validators for external-model intake, LLM transport, tool dispatch, workflow command semantics, fixed-context policy, or other unsupported evidence kinds.
7. Prove source, extractor, rule, or obligation universes universally exhaustive.
8. Establish proposition truth, graph completeness, ALLOW/DENY, audit-gate authorization, or production approval.
9. Provide atomicity across the source, assurance, epistemic, dossier, reconciliation, and observation stores, or an external trust anchor for the ledger.

Exact-source CI validation details will be appended after the workflow runs against the resulting branch head.

# AE-32C M7.5.24 — Persisted Cross-Layer Composition Orchestrator

**Status:** Implemented; CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.23 — Cross-Layer Execution and Semantic-Qualification Composition  
**Scope:** retrieve persisted M7.5.14 and M7.5.18 records, invoke their existing verification paths through M7.5.14 and M7.5.21, then compose the actual operation results  
**Authority:** orchestration and derived inspection only; no epistemic or decision authority

## 1. Purpose

M7.5.23 accepts four mappings, including two replay-result mappings. Its content and cross-layer checks do not authenticate the origin of those supplied results.

M7.5.24 adds an explicit orchestration adapter. It does not replace the underlying verifiers and does not make their independent stores transactional.

## 2. Public API

Module: `audit_engine/semantic_audit/epistemic/obligation_composition_orchestrator.py`

Public functions:
- `verify_persisted_cross_layer_obligation_composition(...)`
- `verify_orchestrated_obligation_composition(...)`

Error:
- `ObligationCompositionOrchestrationError`

The orchestration API accepts persisted record identifiers, store handles, and the live verification context required by the existing APIs. It does **not** accept caller-supplied execution replay or qualification consumer result mappings.

## 3. Operation order

1. Retrieve the M7.5.14 execution reconciliation from its ledger.
2. Retrieve the M7.5.18 qualification envelope and verify its record identity.
3. Invoke `verify_execution_obligation_reconciliation(...)`, which checks ledger integrity and rebuilds the execution reconciliation against the supplied source, extractor, dossier, assurance, and epistemic context.
4. Derive the eight-dimensional qualification currentness context from the live claim, plan, coverage manifest, qualification, observation bundle, and source manifest.
5. Invoke `verify_persisted_qualification_reconciliation_for_consumer(...)`. M7.5.21 independently derives the context again, runs its currentness preflight, and invokes historical semantic replay only when the record is current.
6. Pass the two verifier results and the retrieved reconciliation records to M7.5.23.
7. Return the composition and the component operation results in a content-addressed orchestration envelope.

A M7.5.21 invalidation is retained as `BLOCKED_INVALIDATED`; it is not bypassed by the orchestrator.

## 4. Persistence and consistency boundaries

- M7.5.14's ledger stores its reconciliation, not all inputs needed to replay it. The caller must supply the original verification context.
- M7.5.18 stores its reconciliation, qualification, and observation bundle in one ledger envelope. Currentness still depends on live artifacts supplied to M7.5.21.
- The orchestration reads and verifies independent stores sequentially. It does not provide an atomic snapshot across the execution ledger, qualification ledger, consumer-check ledger, dossier, assurance store, or epistemic store.
- A failure after a prior store operation may leave that operation's append-only event recorded. The orchestrator does not roll back independent ledgers.
- `verify_orchestrated_obligation_composition(...)` checks the returned envelope and embedded composition content digests only. It explicitly does not claim semantic replay; replay requires rerunning the orchestration with live stores and context.

## 5. Validation strategy

Dedicated tests cover:
- persisted-record retrieval and identity binding;
- execution replay before qualification currentness/replay;
- derivation of currentness context inside the orchestration boundary;
- blocked-invalidated qualification composition without semantic replay;
- missing records and malformed persisted envelopes;
- orchestration-envelope tampering;
- preservation of M7.5.14, M7.5.17, M7.5.21, M7.5.22, and M7.5.23 regressions.

Workflow: [M7.5.24 persisted composition orchestrator](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_24_persisted_composition_orchestrator.yml)

## 6. Authority boundaries

The orchestration does not establish:
- epistemic evidence acceptance or semantic truth;
- proposition truth or graph completeness;
- assurance success;
- audit decision authority or ALLOW/DENY;
- release or production approval.

The consumer identity and operation remain caller-declared. The component ledgers remain independent, and their hashes do not authenticate the external caller or create a trust anchor.

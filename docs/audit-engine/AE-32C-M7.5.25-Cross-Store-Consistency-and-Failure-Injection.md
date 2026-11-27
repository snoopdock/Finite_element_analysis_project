# AE-32C M7.5.25 — Cross-Store Consistency and Failure-Injection Audit

**Status:** Implemented and CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.24 — Persisted Cross-Layer Composition Orchestrator  
**Scope:** deterministic TOCTOU failure injection around qualification replay and execution/qualification orchestration  
**Authority:** consistency diagnostics and fail-closed replay; no cross-store transaction or decision authority

## 1. Audit findings

### 1.1 Qualification preflight-to-replay race

Before M7.5.25, M7.5.21 performed one currentness preflight, then invoked historical semantic replay. A concurrent invalidation appended after the preflight could therefore occur before or during replay without being observed by the consumer operation before it returned `REPLAY_VERIFIED`.

The qualification reconciliation ledger's append-only behavior and hash-chain integrity do not serialize its currentness evaluation with the independent semantic replay operation.

### 1.2 Execution-side staleness window

Before M7.5.25, M7.5.24 replay-verified the execution reconciliation and then performed qualification currentness/replay. A change to a dossier or another execution-side dependency during that interval could make the earlier execution verification stale by the time composition was produced.

The independent stores do not provide a shared snapshot or transaction.

## 2. Bounded hardening

### 2.1 Qualification currentness bracketing

M7.5.21 now performs:
1. Existing consumer preflight, which durably records the consumer check.
2. A second currentness evaluation immediately before semantic replay.
3. Historical semantic replay only if the second evaluation remains `CURRENT`.
4. A post-replay currentness evaluation.
5. Return `REPLAY_VERIFIED` only if post-replay currentness remains `CURRENT`.

If invalidation is observed between the first preflight and the second evaluation, replay is not invoked and the consumer raises `QualificationConsumerReplayError(qualification_invalidated_before_semantic_replay)`.

If invalidation is observed during replay, replay may already have executed, but the consumer raises `QualificationConsumerReplayError(qualification_invalidated_during_semantic_replay)`. It does not return a current `REPLAY_VERIFIED` result. The invalidation remains durable in the append-only qualification ledger.

A blocked result from the original preflight remains blocked without replay, as before.

### 2.2 Execution replay bracketing

M7.5.24 now performs a second M7.5.14 execution replay after the M7.5.21 consumer operation.

- A postflight execution verification failure aborts composition.
- Different preflight/postflight replay results abort composition.
- The returned composition uses the postflight execution replay result.
- The orchestration envelope includes an `execution_replay_bracket` diagnostic with both successful checks and an explicit `atomic_cross_store_snapshot: false`.

This detects execution-side drift observed during the qualification operation. It does not prove that every store or source remained unchanged at every instant.

## 3. Failure-injection validation

New tests: `tests/semantic_graph/test_m7525_cross_store_consistency.py`.

They inject deterministic invalidations:
- immediately after the recorded consumer preflight and before replay; replay must not be called;
- during historical semantic replay; postflight must reject a current replay result;
- no invalidation; pre-replay and post-replay currentness remain current.

M7.5.24 tests also inject an execution-side postflight failure after qualification consumption and assert that composition is not produced.

The real multi-ledger integration test remains in the M7.5.24 suite. Existing M7.5.14, M7.5.17, M7.5.21, M7.5.22, and M7.5.23 regressions remain part of the same workflow.

Workflow: [M7.5.24/M7.5.25 cross-layer consistency validation](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_24_persisted_composition_orchestrator.yml)

## 4. Validation result

Workflow: [M7.5.24/M7.5.25 cross-layer consistency validation](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45972676464)

- Exact tested revision: `93416d3c63a22ab76db22eab02ac38cc8b4e3086`.
- Python 3.11 compilation: passed.
- M7.5.24 orchestration suite: 9 passed.
- M7.5.14 execution reconciliation regression: 7 passed.
- M7.5.17 qualification reconciliation regression: 12 passed.
- M7.5.21 currentness-gated consumer regression: 5 passed.
- M7.5.22 dependency-boundary regression: 5 passed.
- M7.5.23 composition regression: 11 passed.
- M7.5.25 failure-injection tests: 3 passed.
- Complete M7.5 regression: 252 passed.

The workflow completed successfully on the exact tested revision. The failure-injection tests demonstrate that invalidation between preflight and replay prevents replay, invalidation during replay prevents a current replay result from being returned, and execution-side postflight failure prevents composition.

## 5. Failure and interruption semantics

- If the first execution replay fails, qualification consumption and composition do not proceed.
- If qualification preflight or replay fails, composition does not proceed.
- If qualification invalidation is observed during or immediately before replay, no current consumer result is returned.
- If the second execution replay fails, composition does not proceed.
- Consumer preflight and invalidation events already appended to their respective ledgers are not rolled back.
- The orchestrator does not attempt compensation or deletion across independent stores.

## 6. Explicit residual limitations

This is **race-window reduction and detection**, not atomicity.

- An invalidation may still occur after the final post-replay currentness check and before the caller acts on the returned result.
- An execution-side dependency may change after the postflight execution replay.
- A transient change that is reverted before the next check may evade bracketing detection.
- Qualification currentness dimensions bind declared identifiers and digests; they do not create an external trust anchor or prove all filesystem/store state is globally frozen.
- The independent SQLite ledgers are not coordinated under a distributed transaction or shared lock.
- No crash-recovery protocol spans the execution, qualification, consumer-check, dossier, assurance, and epistemic stores.
- The orchestration does not provide a globally linearizable snapshot.

A stronger guarantee would require a separately designed snapshot/version protocol or a single transactional authority over all relevant state. M7.5.25 deliberately does not introduce one.

## 7. Authority boundaries

M7.5.25 does not establish evidence acceptance, proposition truth, graph completeness, assurance success, ALLOW/DENY, audit authorization, release approval, or production approval. A successful replay bracket remains a bounded consistency observation, not a decision.

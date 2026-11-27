# AE-32C M7.5.20 — Downstream Qualification Currentness Consumer Gate

**Status:** Implemented and CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.19 — Qualification Reconciliation Currentness Gate  
**Authority:** append-only recording of consumer currentness preflights only; no semantic replay, evidence acceptance, assurance result, or authorization

## 1. Purpose

M7.5.19 provides a fail-closed currentness check for a persisted qualification reconciliation. Before M7.5.20, a downstream component could call that gate, but there was no explicit consumer identity, declared operation, or durable record that the consumer had performed the check.

M7.5.20 adds a separate append-only consumer-check ledger and a single public preflight operation. It records which declared consumer and operation checked which reconciliation, the currentness outcome, the invalidation history visible at check time, and a digest of the supplied eight-dimensional context.

## 2. Public API

Module: `audit_engine/semantic_audit/epistemic/qualification_consumer_gate.py`

- `QualificationConsumerCheckStore`
- `QualificationConsumerGateError`
- `evaluate_qualification_reconciliation_for_consumer(...)`

The API is exported from `audit_engine.semantic_audit.epistemic`.

Required inputs:
- Persisted reconciliation ID.
- Non-empty caller-declared consumer ID.
- Non-empty caller-declared operation.
- M7.5.18 reconciliation store.
- M7.5.20 consumer-check store.
- Current context containing exactly the eight M7.5.18 dimensions.

The function calls the M7.5.19 currentness gate first. If drift is present, M7.5.19 must durably append its invalidation before the consumer check is recorded. If currentness evaluation fails, no consumer check is recorded. If the consumer ledger cannot append, the operation raises rather than returning a successful preflight.

## 3. Preflight outcomes

- `CURRENTNESS_CONFIRMED`: M7.5.19 returned `CURRENT` for the supplied context and no invalidation exists in the reconciliation history.
- `BLOCKED_INVALIDATED`: M7.5.19 returned `INVALIDATED`, including when the caller later supplies the original context after an earlier invalidation.

Both outcomes are durable consumer-check events. Repeating the exact same consumer, operation, reconciliation, and context is idempotent. A different consumer, operation, or context produces a different check identity.

The consumer ledger uses canonical JSON, SHA-256 content addressing, an append-only SQLite table, update/delete triggers, a sequential hash chain, bounded capacity without eviction, and integrity verification before reads and writes.

## 4. Required consumer behavior and authority boundary

A downstream consumer must treat `BLOCKED_INVALIDATED` as a hard stop for use of that historical reconciliation. It must not treat `CURRENTNESS_CONFIRMED` as sufficient to consume evidence or make an assurance decision. The consumer must still perform the semantic replay, evidence qualification, assurance evaluation, and separately governed decision checks required by its operation.

The API deliberately returns `downstream_authorization: NOT_EVALUATED` for both outcomes. The consumer ID and operation are caller-declared labels, not authenticated identities. The supplied context is structurally validated by M7.5.19 but its derivation from authentic current artifacts remains the caller's responsibility.

Call the preflight immediately before use and bind the consuming operation to the same artifacts represented by the supplied context. The two ledgers are separate SQLite stores; there is no atomic cross-store transaction. A state change after the preflight can create a time-of-check/time-of-use gap. This milestone does not claim to eliminate that race, enforce that every consumer calls the API, or prevent a consumer from bypassing it.

No coverage dossier, epistemic assertion, assurance record, ALLOW/DENY decision, audit authorization, release approval, or production approval is created or changed by this milestone.

## 5. Structural, behavioral, and adversarial tests

Dedicated tests cover:
- Currentness-confirmed preflight is durably recorded without authorization.
- Drift invalidation is appended before a blocked consumer event.
- Context reversion does not restore consumer eligibility.
- Identical checks are idempotent.
- Consumer and operation identity affect the content-addressed event ID.
- Consumer-ledger capacity exhaustion fails closed.
- Tampering is detected by the hash-chain verifier.
- Invalid consumer identity is rejected.
- Missing reconciliation prevents a consumer event.

## 6. Validation

The dedicated workflow compiles the epistemic package, runs M7.5.20 tests, M7.5.19 currentness tests, M7.5.18 persistence tests, M7.5.17 reconciliation tests, and the complete M7.5 regression on the exact triggering revision.

Validation evidence:
- [M7.5.20 workflow run 45963213105](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45963213105) — success on exact tested revision `7038a5e87f3d44208a4d6646f2e1f1384885a47a`.
- Dedicated M7.5.20 tests: 9 passed.
- M7.5.19 tests: 10 passed.
- M7.5.18 tests: 23 passed.
- M7.5.17 tests: 12 passed.
- Complete M7.5 regression: passed.
- Python 3.11 compilation: passed.

The M7.5.21 exact-head workflow also reruns the M7.5.20 suite and the complete M7.5 regression.

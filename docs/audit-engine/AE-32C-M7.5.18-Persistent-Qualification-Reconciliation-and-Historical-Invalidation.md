# AE-32C M7.5.18 — Persistent Qualification Reconciliation and Historical Invalidation

**Status:** Implemented; exact-head CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.17 — Semantic Qualification-to-Obligation Reconciliation  
**Authority:** immutable storage and currentness/invalidation metadata only; no epistemic coverage or audit-decision authority

## 1. Purpose

M7.5.17 produced a content-addressed, independently replayable reconciliation from semantic evidence qualifications to rule-derived evidence obligations. It did not retain the reconciliation or its exact qualification and observation-bundle inputs in a durable ledger.

M7.5.18 adds a separate append-only SQLite ledger. It stores the reconciliation together with the exact qualification and typed-observation bundle to which it refers. It also records explicit invalidation events when a later context differs from the context captured by the historical record.

The ledger is independent of the coverage-dossier, epistemic-assertion, and assurance stores.

## 2. Stored record and identity

Implementation: `audit_engine/semantic_audit/epistemic/qualification_reconciliation_store.py`

Public APIs:

- `QualificationReconciliationStore`
- `QualificationReconciliationStoreError`
- `persist_verified_qualification_reconciliation(...)`
- `verify_persisted_qualification_reconciliation(...)`

A stored record contains:

- The complete M7.5.17 reconciliation.
- The complete M7.5.16 qualification.
- The complete M7.5.15 typed-evidence observation bundle.
- A context tuple containing the source snapshot ID, plan digest, rule-registry digest, coverage-manifest digest, semantic-contract-registry digest, aggregation-policy-registry digest, qualification digest, and observation-bundle digest.

The record ID is the M7.5.17 reconciliation SHA-256. Before append, the store independently checks canonical digests and all cross-artifact identity bindings. The supported persistence function additionally calls the M7.5.17 semantic replay verifier before writing.

A caller can invoke the lower-level `record(...)` method directly; that method checks content identity and cross-artifact references but does not itself perform source-semantic replay. The supported verified path is `persist_verified_qualification_reconciliation(...)`.

## 3. Append-only event ledger

The SQLite event ledger provides:

- Canonical JSON serialization.
- SHA-256 payload digests.
- Sequential hash-chain links over sequence, event ID, event type, payload digest, and previous event hash.
- Update/delete rejection triggers.
- Stable content-addressed reconciliation IDs.
- Idempotent insertion of identical records.
- Conflict rejection for event-ID reuse with different content.
- A configurable positive maximum event count.
- Full-chain verification, record lookup, event history, and invalidation history.
- Restart recovery by reopening the database and re-verifying the chain.

The storage bound refuses new events; it does not evict or rewrite older history. Invalidation events consume the same event budget as reconciliation records.

## 4. Historical invalidation

An invalidation is a new append-only event. It never changes the original reconciliation record.

The current-context comparison checks eight dimensions:

| Dimension | Invalidation code |
|---|---|
| Source snapshot ID | `SOURCE_SNAPSHOT_CHANGED` |
| Rule-derived plan digest | `RULE_PLAN_CHANGED` |
| Rule-contract registry digest | `RULE_CONTRACT_REGISTRY_CHANGED` |
| Coverage-manifest digest | `COVERAGE_MANIFEST_CHANGED` |
| Semantic evidence-contract registry digest | `SEMANTIC_CONTRACT_REGISTRY_CHANGED` |
| Aggregation-policy registry digest | `AGGREGATION_POLICY_CHANGED` |
| Qualification digest | `QUALIFICATION_CHANGED` |
| Typed observation-bundle digest | `OBSERVATION_BUNDLE_CHANGED` |

If all eight values match, no invalidation event is written. If one or more differ, a content-addressed invalidation event records the exact current context and deterministic reason codes. Repeating the same invalidation is idempotent. A different later context can append a second invalidation event; earlier events remain intact.

The invalidation event is a historical currentness record. It does not claim the old reconciliation was false when created, nor does it rewrite its result.

## 5. Historical replay

`verify_persisted_qualification_reconciliation(...)` retrieves the immutable stored reconciliation, qualification, and bundle, then invokes the M7.5.17 independent semantic replay verifier against caller-supplied:

- Assurance claim.
- Rule-derived plan.
- Coverage manifest.
- Source snapshot manifest.
- Repository root containing the exact source bytes.
- Defeater records, if any.

The replay therefore requires the original source snapshot to remain available. The ledger does not embed all repository source bytes and cannot reconstruct a missing source snapshot. If source bytes have drifted, replay fails rather than silently substituting current bytes.

Currentness comparison and semantic replay are distinct:
- A historical record may still replay against its original source snapshot.
- A newer source, plan, rule registry, contract registry, policy, qualification, or bundle may invalidate its use as the current reconciliation.
- Historical replay success does not cancel an invalidation event.

## 6. Structural, behavioral, and adversarial tests

Dedicated tests in `tests/semantic_graph/test_m7518_qualification_reconciliation_store.py` cover:

- Content-addressed record insertion, idempotence, and restart recovery.
- Cross-artifact binding rejection before append.
- Invalidation without historical mutation.
- Idempotent repeated invalidation.
- Multiple distinct invalidation contexts retained as separate events.
- SQLite update/delete trigger enforcement.
- Database tampering detection by full-chain verification.
- Bounded storage refusing new events without eviction.
- Verified persistence and historical replay through the M7.5.17 semantic verifier.

The workflow also runs M7.5.17's semantic reconciliation tests and the complete M7.5 regression suite.

## 7. Explicit limitations

M7.5.18 does not establish:

1. An external trust anchor, authenticated signer identity, or protection against a privileged database administrator who can rewrite the database and recompute all hashes.
2. Atomic transactions across the qualification ledger, coverage-dossier store, epistemic store, assurance store, or repository.
3. Availability of historical source bytes; replay requires the original snapshot to be supplied.
4. Exhaustiveness or correctness of rule selection, source inventory, extractors, evidence observations, or semantic contracts.
5. That a historical record remains current after any recorded invalidation.
6. Proposition-wide truth, accepted epistemic assertions, `EVIDENCE_BOUND` coverage, ALLOW/DENY, audit authorization, release approval, or production approval.
7. Automatic propagation of invalidation into the coverage dossier, epistemic ledger, or downstream audit decisions.

The hash chain detects accidental or partial tampering within the ledger. It is not a cryptographic signature or external immutability guarantee.

## 8. Validation

Workflow: [M7.5.18 persistent qualification reconciliation](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_18_qualification_reconciliation_store.yml)

The workflow checks Python 3.11 compilation, dedicated M7.5.18 tests, M7.5.17 replay regression, and the complete M7.5 regression on the exact triggering revision.

Do not mark this milestone CI-validated until a successful workflow run is confirmed for the final branch head.

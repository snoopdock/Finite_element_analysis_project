# AE-32C M7.5.2 — Append-only epistemic persistence

**Status:** Implemented; exact-source CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent tranche:** M7.5.1 immutable epistemic contracts  
**Authority:** descriptive persistence only; no inference or decision-gate authority

## 1. Purpose

M7.5.1 defined immutable records but did not persist them. M7.5.2 adds a durable event ledger for evidence assertions and knowledge-gap lifecycle records. It preserves the source contracts rather than normalizing them into one mutable epistemic status per graph entity.

The store is deliberately separate from the earlier `core.epistemic_state_store`. That legacy helper writes a mutable `knowledge_graph.epistemic_states` mapping, merges normalized fields, and can evict records when a configured maximum is exceeded. Those semantics are incompatible with an append-only audit history. The legacy API is not modified by this tranche.

## 2. Storage model

Implementation: `audit_engine.semantic_audit.epistemic.store.EpistemicStore`.

Backend: Python standard-library SQLite.

Each event stores:
- monotonically increasing sequence number;
- stable event ID (`record_type:record_id:revision`);
- record type and stable record ID;
- revision number;
- canonical JSON payload and its SHA-256 digest;
- previous event hash and current event hash.

The event hash commits to sequence, event ID, payload digest and previous hash. `verify_integrity()` recomputes the complete chain and payload digests. This detects accidental or out-of-band changes; it is not a digital signature, trusted timestamp, external anchoring mechanism or defense against an attacker who can rewrite the entire database and recompute the chain.

SQLite triggers reject UPDATE and DELETE operations against the event table. These are application-level immutability controls, not a claim that a privileged operator or database administrator cannot replace the database file or schema.

## 3. Identity and duplicate semantics

### Evidence assertions

- `assertion_id` is the stable identity.
- The first record is revision 1.
- Re-submitting the same canonical payload under the same ID is idempotent and returns `False`.
- Reusing the same ID for different content raises `DuplicateRecordError`.
- Supporting and challenging assertions use distinct IDs and coexist; neither overwrites the other.

### Knowledge gaps

- `gap_id` is the stable identity.
- The initial record is revision 1.
- Each lifecycle change appends a new revision; prior payloads remain queryable through `gap_history()`.
- The caller supplies `expected_revision`; stale revisions raise `RevisionConflictError`.
- Subject, kind, scope and discovery method are invariant across revisions.
- Terminal states (`RESOLVED`, `ACCEPTED_RESIDUAL`) cannot be reopened through the current transition API.
- Contract-level requirements still apply: resolved gaps need resolution evidence; accepted residual gaps need disposition and authority.

The store does not rewrite assertions when later evidence challenges them. A new assertion is a new record.

## 4. Bounded storage policy

`max_events` is a hard admission limit. When reached, a new event raises `StorageLimitError`. Existing events are never truncated, evicted or silently deleted. Retention, archival, compaction and multi-database partitioning are not implemented; they require a separately specified preservation and audit policy.

## 5. API surface

- `record_assertion(EvidenceAssertion) -> bool`
- `record_gap(KnowledgeGap) -> bool`
- `transition_gap(KnowledgeGap, expected_revision=...) -> int`
- `latest_gap(gap_id)`
- `gap_history(gap_id)`
- `assertion_history(assertion_id)`
- `event_count()`
- `verify_integrity() -> bool`

The package exports the store and its typed errors. The API is local and synchronous. It performs no network access, solver invocation, inference, completeness evaluation or deterministic-gate mutation.

## 6. Validation obligations

The M7.5.2 test suite covers:
1. coexistence of opposing assertions;
2. idempotent duplicate submission and conflicting-ID rejection;
3. append-only gap lifecycle history;
4. stale-revision and terminal-state rejection;
5. database-level UPDATE/DELETE rejection;
6. hard-cap behavior without eviction;
7. close/reopen durability and hash-chain verification;
8. detection of out-of-band payload tampering.

These tests are structural and behavioral. They do not establish production durability under power loss, filesystem corruption, concurrent multi-process stress, backup/restore correctness, external authenticity, or a hostile administrator.

## 7. Explicit non-goals

M7.5.2 does not:
- persist `CompletenessClaim` records yet;
- infer truth from absence;
- select FDE, Bayesian, Dempster–Shafer or argumentation semantics;
- resolve contradictions;
- calculate validator independence;
- authenticate evidence producers or timestamps;
- connect epistemic records to audit findings or authorization;
- promote the system to production approval.

## 8. Relationship to later work

M7.5.3 remains responsible for scope-bound completeness evaluation and negative-claim admissibility. Freshness and dependency invalidation, defeaters, common-cause analysis and controlled deterministic consumption remain later tranches. M7.4 remains frozen as `PARTIAL — FROZEN BASELINE`; this work does not reopen or upgrade it.

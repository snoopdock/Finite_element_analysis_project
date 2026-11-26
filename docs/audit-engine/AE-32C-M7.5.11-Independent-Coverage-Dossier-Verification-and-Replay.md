# AE-32C M7.5.11 — Independent Coverage Dossier Verification and Replay

**Status:** Implemented; exact-source M7.5 regression validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.10 — Persistent Coverage Dossiers and Gap Reconciliation  
**Authority:** historical dossier integrity and reproducible evaluation only; no proposition-truth, audit-decision or authorization authority

## 1. M7.5.10 audit disposition

M7.5.10 is accepted as implemented and CI-validated.

- Corrective exact-source workflow: [45906808231](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45906808231)
- Validated implementation commit: `39d2b177f5fc486f1acf1f900303ba18500327c1`
- Result: 111 M7.5 regression tests passed.
- The current branch head after the validation is `4f76c5e55fe835642f5979c2d56893dfc635031f`; the intervening commit only records the successful validation in this specification.

The corrective changes resolve the three earlier failures:
1. Missing persisted gap mappings are classified as unreconciled; an existing stronger evaluator state such as UNKNOWN retains precedence over INCOMPLETE.
2. Gap existence is checked before scope, plan membership and manifest representation.
3. Claim-scope validation is checked before downstream obligation/manifest representation.

The audit also confirmed that the dossier layer uses the public verified `EpistemicStore.gap_records_snapshot()` API rather than private SQLite state. No remaining M7.5.10 defect was found that blocks the next bounded verification tranche.

## 2. Why M7.5.11 exists

M7.5.10 persists a complete capture record and protects its append-only ledger with payload digests and a hash chain. Its existing `verify_dossier_against_current_stores(...)` operation checks ledger integrity and whether the source-ledger tokens still match. It does not independently reconstruct the persisted rule-derived plan and manifest, verify all cross-field semantic relationships, or replay the evaluation.

A valid hash chain establishes that the stored bytes have not changed relative to that chain. It does not establish that the bytes form a semantically coherent dossier. M7.5.11 adds that separate check.

## 3. New API

Module: `audit_engine/semantic_audit/epistemic/dossier_verification.py`

Public API:

- `verify_coverage_dossier_replay(dossier_id, assurance_store, epistemic_store, dossier_store)`

The verifier:

1. Loads the dossier only after the dossier ledger hash chain verifies.
2. Resolves exactly one persisted assurance claim for the dossier's claim ID.
3. Reconstructs the typed rule-derived plan and coverage manifest.
4. Re-derives and verifies the plan against the current built-in, versioned rule registry.
5. Checks that the manifest and persisted evaluation result bind to the same claim, plan and manifest digest.
6. Recomputes the missing-obligation set from the derived obligation universe.
7. Validates captured ledger-token shape and the relationship between before/after tokens and the capture-consistency flag.
8. Validates gap inventory identity, revision, event-hash shape and stable ordering.
9. Revalidates every persisted gap mapping against inventory scope, derived-plan membership and assessed-manifest representation.
10. Recomputes in-scope, out-of-scope and unreconciled gap partitions.
11. Recomputes the overall status using M7.5.10's precedence rules.
12. When both current source-ledger tokens still equal the captured after-tokens, compares the current gap inventory and deterministically replays M7.5.8 evaluation. Any mismatch is rejected.

The existing drift-check API remains available and unchanged.

## 4. Replay and drift semantics

The verifier distinguishes three questions:

- **Dossier-ledger integrity:** does the append-only dossier ledger's hash chain verify?
- **Historical semantic integrity:** do the persisted plan, manifest, result, gap inventory, mappings, tokens and status agree with their contracts?
- **Current replayability:** do both source ledgers still match the captured after-tokens, allowing the stored evaluation to be replayed against the same state?

A later source-ledger mutation does not erase the historical dossier or automatically make its stored structure incoherent. It does prevent a claim that the old evaluation has been replayed against the current stores. In that case the verifier reports source drift and skips replay.

The replay is deterministic only within the pinned source code, built-in registry, persisted claim and unchanged source-ledger snapshots. It is not a proof that the source inventory, selected rule set, extractor inventory or obligation universe is exhaustive.

## 5. Structural and behavioral tests

New suite: `tests/semantic_graph/test_m7511_dossier_verification.py`

The tests cover:

- Successful semantic verification and exact replay when source ledgers are unchanged.
- Historical semantic verification after source drift, with replay correctly skipped.
- Detection of a semantically forged manifest even when an altered dossier payload is re-hashed into a valid local ledger chain.
- Detection of a forged overall status even when the altered payload is re-hashed into a valid local ledger chain.

The re-hashing tests are deliberate: they demonstrate that the semantic verifier is not merely delegating all assurance to the existing hash-chain check.

## 6. Cross-ledger consistency decision

M7.5.11 does not introduce a distributed transaction or claim atomic writes across the epistemic, assurance and dossier databases. For the current append-only capture contract, M7.5.10's before/after token checks are retained as optimistic mutation detection. The dossier records the exact tokens and explicitly reports whether capture remained stable.

This is not a general atomicity guarantee and must not be described as one. A future requirement for atomic multi-ledger writes, rollback across databases, or a single externally anchored commit would require a separate architecture decision and protocol. It is not silently inferred from token equality.

## 7. Validation

The dedicated workflow `.github/workflows/m7_5_11_dossier_verification.yml` compiles the epistemic package and runs the full M7.5 regression discovery set:

```bash
python -m unittest discover -s tests/semantic_graph -p 'test_m75*.py' -v
```

The workflow checks out the exact triggering commit, uses Python 3.11, and uploads compile/test logs. M7.5.11 must not be marked CI-validated until the run for the final source revision succeeds.

## 8. Explicit limitations

M7.5.11 does not establish:

- Cryptographic authenticity of the repository owner, registry author or ledger administrator.
- Resistance to a privileged actor who can rewrite a ledger and recompute its hashes.
- Exhaustiveness of source, graph, extractor, rule or obligation inventories.
- Semantic correctness of a gap-to-obligation assignment beyond the structural plan/manifest constraints.
- Proposition truth, universal evidence completeness, negative-claim authorization, ALLOW/DENY, production approval or audit-gate authority.
- Atomic transactions across the separate SQLite stores.
- Independent proof of the Python interpreter, SQLite implementation or hash implementation.

M7.5 remains an epistemic assurance subsystem. Any later integration into deterministic audit decisions requires a separately specified authority transition, fail-closed policy and independent acceptance tests.

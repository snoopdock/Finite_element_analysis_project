# AE-32C M7.5.10 — Persistent Coverage Dossiers, Snapshot Binding and Gap Reconciliation

**Status:** Implemented; exact-source CI validation pending.  
**Branch:** `stage1/section-uuids`  
**Scope:** M7.5 epistemic assurance only. No deterministic audit-decision or authorization integration.

## 1. Problem addressed

M7.5.8 evaluates a caller-supplied `EpistemicCoverageManifest` against persisted assurance and epistemic records. M7.5.9 derives an expected obligation universe from caller-selected, versioned AE-32C rules. Before this milestone, neither the plan nor the result was retained as one durable dossier, and the evaluator only examined gaps explicitly attached to assessed obligations.

That left two important omissions:

1. A later process could not recover the exact plan, manifest, evaluation, gap mapping and captured snapshot tokens as one persisted record.
2. A persisted knowledge gap that was never attached to an obligation could escape the M7.5.8 evaluator's claim-relative examination.

## 2. New module and API

Implementation: `audit_engine/semantic_audit/epistemic/coverage_dossier.py`

Public APIs:

- `CoverageDossier`
- `CoverageDossierStore`
- `CoverageDossierError`
- `build_and_persist_coverage_dossier(...)`
- `verify_dossier_against_current_stores(...)`

The dossier stores:

- Full M7.5.9 rule-derived plan, including graph snapshot ID and plan digest.
- Full M7.5.8 manifest, including its expected obligation universe and assessments.
- Explicit gap-to-obligation mapping.
- Complete latest-revision gap inventory captured from the epistemic event ledger.
- M7.5.8 evaluation result.
- Before/after snapshot tokens for the epistemic and assurance ledgers.
- Capture-consistency flag, unreconciled gap IDs and overall dossier status.
- Caller-supplied capture timestamp.

## 3. Gap reconciliation contract

Every gap present in the captured epistemic ledger must be mapped to one or more obligations in the derived plan. Each mapping must also be represented by the corresponding assessed `CoverageObligation.gap_ids`.

- A mapping to a nonexistent gap is rejected.
- A mapping outside the derived obligation universe is rejected.\n- A gap whose persisted scope differs from the assurance claim scope cannot be reconciled to that claim.
- A mapping not reflected in the manifest assessment is rejected.
- A persisted gap omitted from the mapping is retained in `unreconciled_gap_ids` and forces overall status `INCOMPLETE`.
- Gaps are not silently discarded or inferred to be resolved.
- The M7.5.8 evaluator continues to determine the state of gaps explicitly attached to obligations.

The complete gap inventory is provided by the public `EpistemicStore.gap_records_snapshot()` API. It verifies the event hash chain and returns every latest gap revision in stable gap-ID order from one SQLite read transaction. The dossier layer no longer accesses the store's private connection or duplicates its table schema.

## 4. Persistence and recovery

`CoverageDossierStore` is a separate SQLite append-only ledger. It has:

- Stable dossier IDs.
- Canonical JSON serialization.
- Per-record SHA-256 payload digests.
- A sequential hash chain.
- Update/delete rejection triggers.
- Duplicate-ID idempotence for identical content and rejection for conflicting content.
- A bounded record count that refuses new writes instead of evicting history.
- Integrity verification, lookup and ordered history APIs.

A dossier survives closing and reopening the store. Recovery reads the persisted payload only after verifying the dossier ledger's full chain.

## 5. Snapshot binding and concurrency semantics

The dossier captures both source-ledger tokens before and after gap inventory and coverage evaluation. If either token changes during the capture interval, `snapshot_consistent` is false and overall status is `UNKNOWN`.

The verifier compares current source-ledger tokens with the captured after-tokens. A later mutation is reported as snapshot drift; the historical dossier is not rewritten.

**Important transaction boundary:** the assurance and epistemic ledgers are independent SQLite databases, and the dossier is a third database. M7.5.10 does not claim a distributed atomic transaction. Before/after token comparison is optimistic concurrency detection, not cross-database locking or consensus. A mutation after the final token read is detectable by a later current-snapshot verification, but cannot retroactively change the immutable capture record.

## 6. Validation

New tests: `tests/semantic_graph/test_m7510_coverage_dossier.py`

The tests cover:

- Restart/recovery of a persisted dossier.
- Full persisted gap inventory through the public verified `gap_records_snapshot()` API.
- Omitted/unreconciled gap detection.
- Rejection of invalid or unrepresented gap mappings.
- Epistemic-ledger drift after capture.
- Assurance-ledger drift after capture.
- Out-of-band tampering detection.
- Append-only update/delete protection.

The workflow `.github/workflows/m7_5_10_coverage_dossier.yml` compiles the epistemic package and runs the complete `test_m75*.py` regression set on the exact triggering revision. The milestone must not be called CI-validated until that run succeeds.

## 7. Explicit limitations

M7.5.10 does not establish:

- Exhaustiveness of source inventory, graph inventory, extraction or rule selection.
- That every persisted gap has been correctly classified or assigned to the semantically correct obligation; it only detects missing/invalid mappings against the supplied derived universe.
- Atomic consistency across the separate epistemic, assurance and dossier databases.
- External authentication of the rule registry or event-ledger administrators.
- Protection against a privileged actor who can rewrite the database and recompute every hash.
- Proposition truth, universal evidence completeness, ALLOW/DENY, production approval or audit-gate authorization.
- Integration into deterministic audit decisions.

The graph snapshot ID is retained through the rule-derived plan and its digest; M7.5.8's existing manifest schema remains unchanged.

## 8. Next engineering boundary

Before M7.5.11 or any decision-gate integration, decide whether cross-ledger atomicity is required. If atomicity is required, the architecture must consolidate the relevant records into one transactional store or introduce a formally specified commit protocol; simply comparing tokens is insufficient.

# AE-32C M7.5.7 — Provenance-Backed Assurance Evaluation

**Status:** Implemented and CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.1–M7.5.6  
**Validated source revision:** `dbe2f63aa9756408883019380bfaf3df09e05191`  
**Validation run:** [45901975443](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45901975443)  
**Authority:** Evaluation-only; no proposition-truth inference and no audit-gate authority

## 1. Problem statement

M7.5.5 introduced assurance claims, argument links, defeaters and defeater events. Its evaluator accepts caller-supplied `available_evidence_ids` and a caller-supplied freshness mapping. This is useful as a pure contract evaluator, but those inputs are not themselves proof that the evidence is persisted or that the provenance nodes are fresh.

M7.5.6 added recursive provenance freshness closure. M7.5.7 connects these capabilities without changing the existing pure `evaluate_assurance` API.

## 2. Objective

Add `evaluate_persisted_assurance(claim_id, assurance_store, epistemic_store)` to:

1. Load typed assurance records from the append-only assurance ledger.
2. Resolve every evidence ID used by argument links, defeaters and defeater events against persisted `EvidenceAssertion` / `EvidenceRef` records.
3. Reject missing or conflicting evidence metadata.
4. Require evidence references to bind to the assurance claim's source snapshot and require a persisted assertion for the same proposition and scope.
5. Require each evidence node's dependency edges to match its persisted snapshot, producer, method and optional artifact digest metadata.
6. Derive freshness from `EpistemicStore.freshness_closure()` for every referenced evidence node and every provenance node named by an argument link.
7. Return `INCOMPLETE` if evidence, provenance, integrity or cross-ledger consistency cannot be established.

## 3. Evidence provenance convention

For each `EvidenceRef` with ID `E`, the provenance node is `evidence:E`. Its exact outgoing dependency set must encode:

- `source_snapshot` → `snapshot:<source_snapshot_id>`
- `evidence_producer` → `producer:<producer_id>`
- `evidence_method` → `method:<method_id>`
- `artifact_digest` → `artifact-sha256:<artifact_sha256>`, when a digest is present

`EpistemicStore.record_assertion_dependencies(assertion)` records these edges and the closed manifest. It does not declare the metadata nodes terminal. Each terminal metadata node must receive an explicit empty manifest; otherwise recursive freshness is `UNKNOWN`.

This convention makes the evidence's declared metadata dependencies inspectable. It does not authenticate those metadata values or prove that the declared set is exhaustive.

## 4. Cross-ledger read consistency

The assurance and epistemic ledgers remain separate SQLite databases; no distributed or cross-database transaction is introduced.

The evaluator uses verified `(event_count, head_hash)` tokens. It captures starting tokens in assurance-then-epistemic order, reads both ledgers and computes freshness, then captures ending tokens in reverse order. If either token changes, the two ledgers cannot be treated as one stable evaluation view and the result is `INCOMPLETE`.

The read intervals overlap. If both ledgers remain unchanged throughout their respective intervals, the evaluation has a common stable observation window. This is optimistic read validation, not atomic commit, distributed consensus, signed provenance, or administrator-resistant tamper proof.

## 5. Result contract

`PersistedAssuranceResult` reports:

- requested claim ID and resolved `AssuranceClaim`, when found;
- existing `ArgumentAssessment`;
- per-node `FreshnessResult` records;
- missing evidence IDs;
- explicit reasons for incomplete evaluation;
- whether both ledger version tokens remained stable.

Missing/ambiguous claim, absent evidence, conflicting EvidenceRef metadata, proposition/scope mismatch, snapshot mismatch, missing or mismatched evidence dependency edges, non-fresh closure, integrity/read failure, and concurrent ledger changes all fail closed to `INCOMPLETE`.

The existing pure `evaluate_assurance` remains available for isolated contract testing. It is not silently upgraded or removed.

## 6. Structural and behavioral tests

The M7.5.7 suite checks:

- successful store-backed evaluation with persisted evidence and fresh recursive closure;
- evidence IDs that are not present in persisted assertions;
- missing terminal manifests;
- transitive invalidation of an evidence producer;
- source-snapshot mismatch;
- proposition/scope mismatch between persisted evidence assertions and the assurance claim;
- conflicting metadata for one evidence ID;
- persistence and freshness of defeater-resolution evidence;
- a ledger write during evaluation;
- absent assurance claim behavior.

The workflow continues to run all M7.5.1–M7.5.6 regression suites before the M7.5.7 suite.

## 7. Boundaries and limitations

1. The two ledgers are not transactionally coupled. Optimistic token checks detect writes during evaluation but do not create a shared transaction or durable cross-ledger commit.
2. Hash chains detect inconsistent event history relative to the stored chain; they do not authenticate the chain head against an external trust anchor.
3. The evaluator trusts the persisted EvidenceRef metadata as recorded; it does not verify the producer, method, source URI, artifact bytes or digest against an external system.
4. Evidence independence is not inferred from distinct IDs or producer labels.
5. The evidence dependency convention covers snapshot, producer, method and optional artifact digest. It does not establish completeness of all possible provenance dimensions.
6. The caller-authored argument premise IDs and warrant IDs are not resolved against a formal premise/warrant registry in this milestone.
7. No automatic argument/defeater discovery or completeness proof is introduced.
8. `SUPPORTS_WITHOUT_OPEN_DEFEATERS` remains an assessment of the supplied persisted argument structure only. It is not proposition truth, proof, production approval, ALLOW, DENY, or an audit-gate decision.

## 8. Exit criterion

The M7.5.7 implementation and CI exit criterion are met for the exact Stage1 revision recorded above. The dedicated suite and all M7.5.1–M7.5.6 regression suites passed. See [AE-32C-M7.5.7-Validation-Record-45901975443.md](AE-32C-M7.5.7-Validation-Record-45901975443.md) for exact evidence.

## 9. Implementation and validation result

The implementation adds:

- `AssuranceStore.records_snapshot()` to reconstruct typed assurance records from one verified ledger snapshot;
- `EpistemicStore.assertion_records_snapshot()` to retrieve typed evidence assertions from one verified ledger snapshot;
- verified `snapshot_token()` methods for optimistic cross-ledger read validation;
- `EpistemicStore.record_assertion_dependencies()` to bind evidence IDs to declared snapshot, producer, method and optional artifact-digest nodes;
- `evaluate_persisted_assurance()` and `PersistedAssuranceResult` as the store-backed API.

Validation on the exact revision:

- M7.5.1: 14 passed
- M7.5.2: 9 passed
- M7.5.3: 14 passed
- M7.5.4: 12 passed
- M7.5.5: 8 passed
- M7.5.6: 9 passed
- M7.5.7: 10 passed
- **Total: 76 passed**
- Python 3.11 compile: passed
- Workflow run: `45901975443`
- Artifact: `m7-5-epistemic-validation-45901975443-1`
- Artifact SHA-256: `bb509455cf69092ff7c1bcfad8fde5d14618684e32f763a0c6bdc64f45c161c2`

Passing tests establish CI validation only, not production approval.

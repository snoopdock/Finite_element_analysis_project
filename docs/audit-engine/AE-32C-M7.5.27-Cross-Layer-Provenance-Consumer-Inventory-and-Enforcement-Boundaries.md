# AE-32C M7.5.27 — Cross-Layer Provenance Consumer Inventory and Enforcement Boundaries

**Status:** Implemented; exact-head CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.26 — Cross-Layer Snapshot Identity and Provenance Contract  
**Baseline revision:** `54f926ac00d5f252383c3c8c9fbbf57f93a24e16`  
**Scope:** inventory production consumers of the M7.5.26 provenance envelope, classify assurance-level requirements, and guard against accidental or semantically unsafe integration  
**Authority:** architecture inventory and structural dependency guard only

## 1. Decision

**No production downstream consumer of the M7.5.26 cross-layer provenance API was identified in the audited repository code. No new integration or global enforcement gate is justified by the current contracts.**

M7.5.26 currently provides a verifier and a content-seal checker. It is not wired into the M7.5.21 qualification consumer, M7.5.24 composition orchestrator, execution-obligation reconciliation, coverage dossier, dossier replay, or persisted-assurance evaluator.

This is a meaningful boundary, not a missing integration to be filled speculatively. Those systems have distinct inputs and semantics. Requiring the M7.5.26 envelope from them without a demonstrated contract dependency would expand coupling and could imply guarantees the envelope does not provide.

## 2. Inventory

The audit examined the M7.5.26 implementation, package facade, M7.5.21/M7.5.24 consumers, the M7.5.22 dependency inventory, and the adjacent persisted-assurance and dossier paths. The structural test scans Python production code under `audit_engine/`, `tools/`, and `decision_memory/` for imports and references to the M7.5.26 API and assurance-level fields.

| Component | Actual relationship to M7.5.26 | Classification | Enforcement decision |
|---|---|---|---|
| `cross_layer_snapshot_provenance.py` | Defines `verify_cross_layer_snapshot_provenance(...)` and `verify_cross_layer_snapshot_provenance_envelope(...)` | Provenance producer/verifier | Not a downstream consumer |
| `verify_cross_layer_snapshot_provenance_envelope` | Checks the envelope content seal; explicitly reports `source_state_replay_performed = false` and `downstream_authorization = NOT_EVALUATED` | Seal-only verifier | Must not be treated as source-state replay |
| `qualification_reconciliation_consumer.py` (M7.5.21) | Consumes persisted qualification reconciliation and live qualification context; performs currentness checks and semantic replay | Qualification consumer | No M7.5.26 dependency |
| `obligation_composition_orchestrator.py` (M7.5.24) | Replays persisted execution and qualification records, brackets the qualification operation with execution replay, and composes the results | Cross-layer obligation orchestrator | Consumes underlying artifacts, not the M7.5.26 envelope |
| `execution_obligation_reconciliation.py` (M7.5.14) | Reconstructs execution reconciliation from source manifest, inventory, report, dossier, and stores | Execution reconciliation | No cross-layer envelope dependency |
| `coverage_dossier.py`, `dossier_verification.py` | Build and replay coverage dossiers against assurance and epistemic stores | Coverage dossier path | Remains independent |
| `persisted_assurance.py` | Evaluates persisted assurance records, assertions, provenance dependencies, and freshness | Persisted assurance | Remains independent |
| `qualification_reconciliation_store.py` and `qualification_consumer_gate.py` | Persist, replay, and currentness-gate qualification reconciliation | Qualification persistence/gate | No M7.5.26 envelope dependency |
| `epistemic/__init__.py` | Publicly re-exports epistemic APIs | Package facade | Does not re-export M7.5.26 verifier APIs |
| `test_m7526_cross_layer_snapshot_provenance.py` | Calls the two M7.5.26 APIs to test their behavior | Test caller | Not a production consumer |

The M7.5.22 inventory remains applicable: coverage dossier, dossier replay, and persisted assurance do not consume qualification-reconciliation records. M7.5.27 does not alter that boundary.

## 3. Assurance-level interpretation and consumer contract

M7.5.26 distinguishes declared cross-artifact identity from replay of the Git-backed source state. A future consumer must preserve that distinction.

| Consumer requirement | Minimum acceptable M7.5.26 result | What the result does **not** establish |
|---|---|---|
| Display or inspect declared cross-artifact bindings | `DECLARED_ONLY` may be accepted if visibly retained as declared-only | Source checkout reproduction, producer authenticity, atomicity, authorization |
| Assert that the supplied checkout reproduced the manifest's Git source state at replay time | Require `SOURCE_STATE_REPLAY_VERIFIED` from `verify_cross_layer_snapshot_provenance(..., repository_root=...)` | A later immutable state, external LFS payload verification, recursive submodule verification, producer authenticity, atomic cross-store snapshot |
| Validate a previously produced envelope's content seal | `verify_cross_layer_snapshot_provenance_envelope(...)` may confirm content binding | It does not replay the repository or stores and cannot upgrade `DECLARED_ONLY` to `SOURCE_STATE_REPLAY_VERIFIED` |
| Require a globally consistent read across independent SQLite stores | Neither assurance level is sufficient | M7.5.26 explicitly preserves `atomic_cross_store_snapshot = false` |
| Authenticate the origin of artifacts or their producer | Neither assurance level is sufficient | M7.5.26 has `trust_anchor = NONE` |
| Authorize downstream action, evidence acceptance, proposition truth, release, or production | Neither assurance level is sufficient | Downstream authorization remains `NOT_EVALUATED`; authority fields remain false |

**Required future integration rule:** a consumer that needs source-state reproduction must invoke the full verifier with the relevant repository checkout and require `SOURCE_STATE_REPLAY_VERIFIED`. It must not infer that status from a content seal, matching identifiers, a caller-supplied label, or the envelope-only checker. A consumer that only needs declared binding may retain `DECLARED_ONLY`, but must not rename or promote it.

No current production API has been shown to require either integration path. This table is a contract for evaluating future requests, not an implementation of a universal gate.

## 4. Bypass and misinterpretation boundaries

The following are intentional, documented boundaries:

1. The M7.5.26 verifier is directly importable from its module, but it is not re-exported through the epistemic package facade.
2. The M7.5.26 envelope checker verifies the content seal only. It does not call source-state replay or query persisted stores.
3. The M7.5.24 orchestrator independently replays M7.5.14 execution reconciliation and invokes the M7.5.21 qualification consumer. It does not accept an M7.5.26 envelope.
4. Existing M7.5.21 historical replay and other direct APIs remain callable according to their own contracts. M7.5.27 does not globally intercept Python calls or impose a new gate.
5. External callers, dynamically imported code, reflection, and non-Python consumers cannot be enumerated or intercepted by this source-level repository audit.

A future production import or reference to the M7.5.26 API or assurance-level fields must update the consumer inventory and tests in the same change. The new structural guard makes unreviewed in-repository integrations fail CI within the audited production roots.

## 5. Structural guard

New test: `tests/semantic_graph/test_m7527_cross_layer_provenance_consumer_inventory.py`

The test:
- Scans production Python under `audit_engine/`, `tools/`, and `decision_memory/` for imports and references to M7.5.26 verifier APIs and assurance-level fields.
- Locks the known independent consumer modules against accidental M7.5.26 dependencies.
- Confirms the epistemic package facade does not re-export the verifier as a general-purpose gate.
- Confirms M7.5.24 does not accept or invoke the M7.5.26 envelope.
- Confirms the envelope-only checker has no repository-root replay input and cannot claim source-state replay or downstream authorization.
- Confirms the M7.5.26 implementation continues to declare no trust anchor and no atomic cross-store snapshot.

The M7.5.26 behavioral/adversarial suite remains responsible for exercising real declared-only and source-state-replay results, stale-checkout rejection, cross-artifact mismatch, and envelope tampering. M7.5.27 adds no duplicate fixture or weakened substitute for those behavioral tests.

This is a static architecture guard. It does not prove absence of external consumers, runtime reflection, dynamic imports, or non-Python integrations. It does not authenticate consumers.

## 6. Changes and non-goals

M7.5.27 adds only:
- `tests/semantic_graph/test_m7527_cross_layer_provenance_consumer_inventory.py`
- This inventory and enforcement-boundary document.
- A dedicated exact-triggering-revision CI workflow.

It does **not**:
1. Change M7.5.26 verifier semantics or assurance levels.
2. Integrate provenance into M7.5.21, M7.5.24, M7.5.14, coverage dossier, dossier replay, or persisted assurance.
3. Add a global interception layer or mandatory provenance parameter.
4. Add cross-store transactions, distributed locks, or global snapshot atomicity.
5. Add signatures, producer authentication, or an external trust anchor.
6. Verify external Git LFS payload bytes or recursive submodule contents.
7. Establish evidence acceptance, proposition truth, graph completeness, assurance success, ALLOW/DENY, audit authorization, release approval, or production approval.

## 7. Validation

Workflow: [M7.5.27 Cross-Layer Provenance Consumer Inventory](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_27_cross_layer_provenance_consumer_inventory.yml)

The workflow checks out the exact triggering revision and runs:
- Python 3.11 compilation of the epistemic implementation and source snapshot utility.
- Dedicated M7.5.27 structural consumer-inventory tests.
- M7.5.26 provenance behavioral/adversarial regression.
- M7.5.24 orchestration regression.
- M7.5.25 failure-injection regression.
- M7.5.22 qualification-consumer dependency-boundary regression.
- Complete M7.5 regression.

Validation status and exact revision are recorded here after the workflow completes.

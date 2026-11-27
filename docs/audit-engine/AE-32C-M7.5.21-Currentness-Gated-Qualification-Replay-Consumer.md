# AE-32C M7.5.21 — Currentness-Gated Qualification Replay Consumer

**Status:** Implemented; exact-head CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.20 — Downstream Qualification Currentness Consumer Gate  
**Consumer integrated:** persisted qualification-reconciliation semantic replay  
**Authority:** currentness preflight plus semantic replay only; no evidence acceptance, proposition truth, assurance decision, or authorization

## 1. Purpose

M7.5.20 introduced a reusable preflight ledger but did not integrate it into an actual downstream operation. M7.5.21 adds a concrete consumer entry point for persisted qualification-reconciliation replay.

The integration is deliberately narrow. The existing coverage-dossier builder and persisted-assurance evaluator do not consume qualification-reconciliation records in their current contracts. M7.5.21 does not introduce an unrelated dependency into either. It integrates the currentness gate with the existing M7.5.18 persisted-reconciliation replay operation.

## 2. Public API

Module: `audit_engine/semantic_audit/epistemic/qualification_reconciliation_consumer.py`

- `QualificationConsumerReplayError`
- `qualification_consumer_current_context(...)`
- `verify_persisted_qualification_reconciliation_for_consumer(...)`

The API is exported from `audit_engine.semantic_audit.epistemic`.

## 3. Context derivation and binding

The consumer derives the currentness context from live inputs rather than accepting a caller-created digest map as authoritative. It derives and checks:

1. Source snapshot ID against the claim, plan, source manifest, qualification, and observation bundle.
2. Rule-derived plan digest.
3. Rule-contract registry digest.
4. Coverage-manifest digest.
5. Current semantic evidence-contract registry digest.
6. Current aggregation-policy registry digest.
7. Current qualification content digest and its observation-bundle binding.
8. Current typed-observation-bundle content digest and its plan binding.

The caller-supplied context must exactly equal this derived context. A mismatch is rejected before a consumer event is recorded.

The helper verifies content-addressed qualification and bundle identities and key cross-artifact bindings. Full source and semantic correctness remain the responsibility of the independent M7.5.17 replay verifier.

## 4. Consumer sequence

The public consumer performs these steps in order:

1. Derive the eight-dimensional context from the supplied live artifacts.
2. Reject any caller context that differs from the derived context.
3. Invoke the M7.5.20 consumer preflight, which invokes M7.5.19 currentness evaluation.
4. If the reconciliation is `INVALIDATED`, return `BLOCKED_INVALIDATED` without invoking semantic replay.
5. If currentness is `CURRENT`, invoke the existing M7.5.18 `verify_persisted_qualification_reconciliation(...)` operation.
6. Return `REPLAY_VERIFIED` only when that independent semantic replay succeeds.

A semantic replay failure is propagated as a failure; a successful currentness preflight is not converted into a successful replay result. The preflight event remains an accurate record of the currentness check, not a claim that replay succeeded.

## 5. Tests

Dedicated tests cover:
- Currentness-confirmed preflight followed by actual semantic replay.
- A historically invalidated record is blocked and the replay verifier is not called.
- A caller-supplied context that disagrees with live artifacts is rejected before ledger append.
- All eight context dimensions are derived from live artifacts.
- Source bytes changed after preflight cause the independent semantic replay to fail, despite the preflight having been currentness-confirmed.

The M7.5.20, M7.5.19, M7.5.18, and M7.5.17 regression suites remain part of the workflow.

## 6. Scope and limitations

- This is one explicit consumer integration, not global interception of every repository consumer.
- The older `verify_persisted_qualification_reconciliation(...)` entry point remains available for historical replay and can still be called directly. Consumers requiring currentness enforcement must use the new consumer-facing API.
- Coverage-dossier and persisted-assurance operations remain independent because their current interfaces do not consume qualification-reconciliation records.
- The consumer ID and operation are caller-declared labels, not authenticated identities.
- The M7.5.20 and M7.5.18 ledgers remain separate; no atomic cross-store transaction or TOCTOU elimination is claimed.
- `REPLAY_VERIFIED` means the specific persisted qualification reconciliation passed its independent semantic replay under the supplied source context. It does not mean that all qualifications are supported, that evidence is accepted, that the assurance claim passes, or that an audit/release/production decision is authorized.
- No dossier, epistemic assertion, assurance record, ALLOW/DENY decision, or production approval is created or changed.

## 7. Validation

Workflow: [M7.5.21 currentness-gated qualification replay consumer](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_21_qualification_reconciliation_consumer.yml)

The workflow checks out the exact triggering revision, compiles the epistemic package, runs the dedicated M7.5.21 integration tests, and runs M7.5.20 through M7.5.17 plus the complete M7.5 regression.

Do not mark this milestone CI-validated until a successful run is confirmed for the final branch head.

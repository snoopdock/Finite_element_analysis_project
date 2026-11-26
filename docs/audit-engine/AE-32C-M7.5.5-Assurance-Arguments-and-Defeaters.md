# AE-32C M7.5.5 — Assurance Claims, Argument Links and Defeaters

**Status:** Implemented; CI-validated on the exact Stage1 source revision  
**Branch:** `stage1/section-uuids`  
**Source revision:** `5baa282a0dcd0079ff9055a1a1c3c6bf68ad062c`  
**Validation:** [GitHub Actions run 45899503579](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45899503579)  
**Scope:** Typed assurance arguments and append-only persistence. No truth calculus or audit-gate integration.

## 1. Purpose

M7.5.1–M7.5.4 established evidence assertions, knowledge gaps, scope-bound completeness, provenance dependencies, freshness and invalidation. M7.5.5 adds an explicit argument structure so that the engine can record *why* evidence is offered for or against a proposition and what objections remain.

The model is intentionally modest. A support edge is not proof. A challenge edge is not automatically a refutation. An argument assessment is not an audit verdict.

## 2. Typed records

- **AssuranceClaim** identifies a proposition, subject, scope, source snapshot and human-readable statement.
- **ArgumentLink** links a claim to premise identifiers, a warrant, evidence identifiers and provenance nodes. Its relation is either `SUPPORTS` or `CHALLENGES`.
- **Defeater** records an objection. A **REBUTTING** defeater attacks the claim/conclusion; an **UNDERCUTTING** defeater attacks a particular inference link and therefore must name that link.
- **DefeaterEvent** is an append-only disposition event: `RESPOND`, `RESOLVE`, or `ACCEPT_RESIDUAL`.

The model does not assume that an evidence item is independent merely because it has a distinct ID. Independence analysis remains a separate obligation.

## 3. Defeater semantics

An undercutting defeater must target an existing argument link. Defeater evidence must be present before an assessment can be complete.

- A defeater with no event is open.
- `RESPOND` records a response but does not close the objection.
- `RESOLVE` requires response-evidence identifiers. It closes the current defeater state only when those evidence identifiers are available to the evaluator.
- `ACCEPT_RESIDUAL` requires a named authorizer and remains an open objection for argument assessment. It records an authorized residual-risk disposition; it does not establish that the objection is false.

The latest event controls the derived lifecycle state. Event history is retained; no prior event is rewritten. A later response event after a resolution reopens the defeater.

## 4. Assessment outputs

`evaluate_assurance` returns only one of:

- `NO_ARGUMENT`
- `INCOMPLETE`
- `CONTESTED`
- `SUPPORTS_WITH_OPEN_DEFEATERS`
- `SUPPORTS_WITHOUT_OPEN_DEFEATERS`

Missing evidence or any provenance node not explicitly marked `FRESH` yields `INCOMPLETE`. A challenge link yields `CONTESTED`. Open or accepted-residual defeaters prevent the clean-support state.

**Important:** `SUPPORTS_WITHOUT_OPEN_DEFEATERS` means only that the supplied argument structure has support links and no currently open defeaters under the supplied evidence/freshness inputs. It does not mean that the proposition is true, that all relevant defeaters have been discovered, or that the claim is authorized for an audit decision.

## 5. Persistence

`AssuranceStore` is an isolated SQLite append-only ledger for claim, link, defeater and defeater-event records. It provides:

- Canonical JSON payloads.
- Stable event identity and duplicate-content checks.
- Append-only SQL triggers.
- A SHA-256 event hash chain and full integrity verification.
- A configurable hard event bound; exhaustion rejects writes and does not prune history.

This is a local integrity mechanism, not a distributed consensus protocol, signed provenance registry, external timestamping service, or tamper-proof storage guarantee against an administrator who can replace the database and its trust anchor.

## 6. Boundaries and known limitations

1. No automatic discovery or completeness proof for claims, arguments, premises, warrants or defeaters.
2. No formal argumentation calculus (Dung semantics, FDE, Bayesian inference, SAT/SMT, Lean, or other solver) is selected.
3. No confidence score, probability, ranking or truth value is inferred.
4. No automatic transition to ALLOW, DENY, ACCEPTED, or any audit-gate state is provided.
5. The caller supplies the available evidence-ID set and provenance freshness map; this evaluator does not query or authenticate the M7.5.4 store itself.
6. `ACCEPT_RESIDUAL` is recorded with an authorizer but is not a waiver that clears the defeater.
7. The isolated assurance ledger is not yet transactionally coupled to the epistemic provenance ledger. Cross-ledger atomicity and shared event identity are deferred.
8. Structural validity of the argument graph does not establish argument soundness or exhaustiveness.

## 7. Acceptance tests

The M7.5.5 suite checks immutable contract validation, relation typing, undercutter target binding, missing/stale evidence, open/closed/accepted-residual lifecycle behavior, challenge handling, duplicate identity, storage bounds, append-only enforcement and tamper detection.

The exact-source workflow completed successfully on `5baa282a0dcd0079ff9055a1a1c3c6bf68ad062c`:

- M7.5.1: 14 tests passed.
- M7.5.2: 9 tests passed.
- M7.5.3: 14 tests passed.
- M7.5.4: 12 tests passed.
- M7.5.5: 8 tests passed.
- Total: 57 tests passed; Python 3.11 compile step passed.
- Artifact: `m7-5-epistemic-validation-45899503579-1`.
- Artifact SHA-256: `33d637f95fefadc8374fa401637a1acf08668c5cf9e0d0ae328e91802cd81101`.

See [the validation record](AE-32C-M7.5.5-Validation-Record-45899503579.md) for the run and evidence details.

## 8. Exit criteria and validation boundary

The implementation and CI exit criterion for M7.5.5 are met for the exact source revision above. Passing tests do not constitute production approval or authorize consumption by deterministic audit gates. The limitations in Section 6 remain open and must be addressed explicitly before any broader integration.

# AE-32C M7.5.8 — Epistemic Coverage and Unknown-State Assurance

**Status:** Implemented and CI-validated on the exact Stage1 source revision  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.1–M7.5.7  
**Authority:** claim-relative coverage assessment only; no proposition-truth or audit-gate authority

## 1. Why this tranche exists

M7.5.1–M7.5.7 establish evidence records, local completeness claims, provenance freshness, assurance arguments and store-backed evaluation. They do not establish that the set of evidence obligations supplied to an assurance claim is exhaustive.

M7.5.7 resolves evidence identifiers already referenced by persisted argument links and defeaters. It cannot discover an omitted premise, source, extractor obligation or defeater. A complete recursive provenance closure can still be complete only for the dependencies that were declared.

M7.5.8 adds a separate assessment of whether every obligation in an explicitly declared, versioned coverage manifest is accounted for by persisted evidence, unresolved knowledge gaps and freshness results.

## 2. Contract

New types:

- `CoverageObligation`
- `ObligationDisposition`
- `EpistemicCoverageManifest`
- `EpistemicCoverageStatus`
- `EpistemicCoverageResult`

Each manifest binds:
- assurance claim ID, proposition, subject, scope and source snapshot;
- a coverage-registry identity, version and SHA-256 digest;
- an explicit finite set of expected obligation IDs;
- one disposition for each obligation that has been assessed;
- evidence IDs and knowledge-gap IDs attached to each obligation.

Dispositions are deliberately not Boolean. `EVIDENCE_BOUND`, `UNKNOWN`, `UNSUPPORTED`, `EXCLUDED`, `CONFLICTED`, `BLOCKED` and `NOT_ASSESSED` remain distinct.

## 3. Evaluation semantics

The evaluator verifies the persisted assurance claim binding, resolves evidence references against persisted assertions, requires proposition/scope/snapshot agreement, checks recursive provenance freshness, and inspects referenced knowledge-gap state.

A missing expected obligation or absent evidence is `UNKNOWN), not a negative assertion. A challenging assertion is `CONTESTED`. Unsupported, excluded, blocked or unresolved gaps prevent evidence-complete status. Invalidated provenance yields `INVALIDATED`.

The strongest positive result is named `EVIDENCE_COMPLETE_WITHIN_DECLARED_MANIFEST`. It means only that all obligations in this supplied manifest are evidence-bound under the implemented checks. It is not renamed `COMPLETE`, `TRUE`, `SUPPORTED`, `SAFE`, `ALLOW` or `PRODUCTION_APPROVED`.

## 4. Structural and behavioral tests

The dedicated suite tests:
- exact claim/scope/snapshot binding;
- omitted expected obligations;
- explicit unknown and not-assessed states;
- unsupported/excluded obligations;
- missing persisted evidence;
- conflicting/challenging assertions;
- stale recursive provenance;
- unresolved knowledge gaps;
- registry/manifest digest sensitivity.

The workflow runs this suite after M7.5.1–M7.5.7 regression suites.

## 5. Limitations that remain open

1. The coverage registry and manifest are caller-supplied. Their author, signature and authorization are not authenticated.
2. A digest identifies the supplied manifest bytes; it does not prove that the expected-obligation universe is exhaustive.
3. No automatic discovery of omitted obligations, hidden sources, unknown unknowns or undiscovered defeaters is possible from this contract alone.
4. Knowledge gaps not referenced by a manifest obligation are not automatically associated with that obligation.
5. The evaluator does not authenticate source producers, extraction tools, method identities or artifact bytes externally.
6. Separate SQLite ledgers are checked optimistically; no cross-database atomic transaction is created.
7. This tranche does not connect coverage results to deterministic audit gates or negative-claim authorization.

## 6. Required follow-on work

- Bind the coverage registry to a trusted, versioned rule/obligation registry.
- Derive required obligations from rule contracts and source/extractor coverage rather than relying solely on caller-supplied lists.
- Persist coverage manifests and evaluation results as append-only records with cross-ledger consistency.
- Reconcile all in-scope knowledge gaps against expected obligations.
- Add mutation tests showing that omission of a required obligation is detected when the trusted registry changes.
- Only after these controls are validated should a later milestone define controlled consumption by deterministic audit rules.

## 7. Validation result

Exact-source workflow: [45903188231](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45903188231)

- Validated source revision: `7d4ee3e852e627cde02025ae8894362e7e46393e`
- Runtime: Ubuntu 24.04, Python 3.11
- M7.5.8 dedicated suite: 11 passed
- M7.5.1–M7.5.7 regression suites: 76 passed
- Total: 87 passed
- Epistemic package compile: passed
- Artifact: `m7-5-epistemic-validation-45903188231-1`
- Artifact ID: `15156553705`
- Artifact SHA-256: `9119270727485758a81fe67cf594546af95dd2a94d3ba909a684f3472b108d3f`

The initial M7.5.8 workflow attempt failed because the inserted shell command contained doubled line-continuation characters. The workflow was corrected before the successful exact-source validation recorded above. A subsequent hardening change added explicit provenance-edge matching and resolution-evidence validation; this latest run includes those checks. The failed attempt is not counted as validation.

## 8. Validation boundary

Passing tests establish behavior for the supplied manifest and persisted stores. They do not establish that the manifest represents every relevant epistemic obligation, that all unknown unknowns are discoverable, or that the proposition is true. Production approval is not granted.

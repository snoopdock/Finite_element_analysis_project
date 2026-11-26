# AE-32C M7.5.3 — Scope-bound completeness and negative-claim admissibility

**Status:** IMPLEMENTED; exact-source CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.1 epistemic contracts; M7.5.2 append-only persistence  
**Authority:** admissibility checking only; no proposition-truth inference or decision-gate authority

## 1. Problem statement

An empty graph query, missing record, or absence of a finding is not by itself evidence that a proposition is false. A negative claim is admissible only when its subject, predicate, scope and source snapshot match a completeness claim whose enumeration and verification obligations are satisfied, and when the applicable deterministic rule explicitly permits closed-world reasoning for that predicate and scope.

Completeness remains claim-relative. This tranche does not assert that a repository, graph or audit is complete in the abstract.

## 2. Contract strengthening

`CompletenessClaim` now includes:
- `predicate_id`: the predicate for which coverage is being claimed;
- `expected_unit_ids`: the explicit enumerated universe for the declared scope;
- `covered_unit_ids`: the units actually covered by the verification process.

For `SUPPORTED_WITHIN_SCOPE`, the constructor requires:
1. a known denominator;
2. `covered_units == expected_units`;
3. a non-empty predicate identity;
4. an expected-unit manifest whose length equals the denominator;
5. unique covered and expected unit IDs;
6. exact equality of the covered and expected ID sets;
7. evidence references and a verification method;
8. no unsupported constructs;
9. evidence references bound to the same source snapshot as the claim.

A zero-unit scope is representable, but only as an explicit zero-denominator claim with evidence and a verification method. An empty manifest with a nonzero denominator is not complete.

The unit manifest is an auditable enumeration artifact, not proof that the enumerator's model of the world is correct. Its completeness still depends on the source snapshot, enumeration method, parser/reader behavior, and verification independence.

## 3. Negative-claim request and evaluator

Implementation: `audit_engine.semantic_audit.epistemic.evaluation`.

Public API:
- `NegativeClaimRequest`
- `AdmissibilityDecision`
- `evaluate_negative_claim(claim, request)`

The request binds:
- exact subject ID;
- exact predicate ID;
- exact scope ID;
- exact source snapshot ID;
- explicit closed-world rule ID;
- an explicit boolean indicating whether that rule authorizes closed-world inference;
- currently active invalidation triggers.

The evaluator fails closed if any of the following applies:
- subject, predicate, scope or snapshot mismatch;
- completeness status is not `SUPPORTED_WITHIN_SCOPE`;
- denominator is unknown or counts disagree;
- the unit manifest is absent/inexact;
- enumeration evidence or verification method is absent;
- evidence references point to another snapshot;
- exclusions, unsupported constructs or unverified assumptions remain;
- a declared invalidation trigger is active;
- the rule identity is absent or the rule does not explicitly authorize closed-world inference.

The result is an admissibility decision with explicit reasons. A positive result means only that the supplied claim meets these encoded preconditions. It does **not** assert that the negative proposition is true. The caller must still execute the named deterministic rule, preserve its derivation and apply the existing authorization process.

The boolean rule-authorization input is a caller-supplied assertion. This tranche does not yet bind it to a signed/versioned rule-registry artifact or authenticate the caller. That is a later integration obligation.

## 4. Persistence

M7.5.2's append-only SQLite ledger now accepts `CompletenessClaim` records through:
- `record_completeness_claim(claim)`
- `completeness_history(claim_id)`

Completeness records use the same stable identity, canonical payload, duplicate handling, payload digest and event hash chain as assertions and gaps.

The database schema is migrated from the M7.5.2 two-record-type constraint to the three-record-type schema without dropping prior event rows. The migration preserves sequence numbers and hash-chain fields; tests verify the prior chain remains valid after migration and that a completeness record can then be appended.

This is a local SQLite migration, not a distributed or externally anchored migration protocol.

## 5. Validation

The M7.5.3 suite covers:
1. exact unit-manifest accounting;
2. duplicate unit rejection;
3. required predicate identity;
4. explicit zero-unit scope;
5. exact subject/predicate/scope/snapshot matching;
6. explicit closed-world rule authorization;
7. partial/unsupported completeness rejection;
8. exclusions, unsupported constructs and assumptions;
9. active invalidation triggers;
10. snapshot-bound evidence;
11. completeness-record persistence and idempotency;
12. lossless M7.5.2-to-M7.5.3 schema migration.

The workflow also reruns M7.5.1 and M7.5.2 suites to guard the existing contracts and store.

## 6. Explicit non-goals and residual risks

M7.5.3 does not:
- infer that a proposition is false;
- generate a negative finding from an empty graph query;
- automatically promote a claim to `SUPPORTED_WITHIN_SCOPE`;
- prove that the declared unit universe is semantically exhaustive;
- authenticate the enumerator, evidence producer, rule registry or authorization boolean;
- establish independence of enumeration and verification;
- detect all possible invalidation events without an upstream dependency mechanism;
- connect admissibility decisions to audit rules or deterministic gates;
- authorize repairs, publication or production deployment.

A completeness claim can be structurally valid yet wrong because its enumeration method omitted a class of source units, the source snapshot was misidentified, the verification shares the same defect, or the scope was badly specified. M7.5.4's provenance dependency and deterministic invalidation work, followed by M7.5.6's independence/common-cause analysis and M7.5.7's controlled rule consumption, remain necessary before operational negative claims can be relied upon.

## 7. Relationship to the frozen baseline

M7.4 remains `PARTIAL — FROZEN BASELINE`. M7.5.3 neither reopens nor upgrades M7.4. Passing this workflow is implementation evidence for the scoped contracts and evaluator only, not production approval.

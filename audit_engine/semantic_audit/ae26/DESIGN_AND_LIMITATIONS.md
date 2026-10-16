# AE-26 — Language-independent semantic identity and contract evolution

## Purpose

The G9.28 corrective release hardens AE-26 before the Audit Engine enters
AE-27 neurosymbolic proposal work.

It provides:

- one canonical semantic-record construction path;
- explicit entity/occurrence/semantic identity separation;
- semantic IDs independent of occurrence and evidence-source identity;
- semantic producer binding for interface relationships;
- deterministic semantic fingerprints;
- separate authoritative and hypothesis projections;
- complete evolution reporting for relationships, entities, policies, and
  coverage;
- deterministic handling of parallel interface variants;
- source-replay verification of serialized projections and diffs.

## Why the corrective release was required

The first G9.28 run failed one test because the test selected the first
lexicographically sorted edge rather than the modified occurrence. That was a
test defect.

The deeper review also identified that the first implementation could produce:

1. a semantic fingerprint that changed when policy/coverage state changed
   without a corresponding semantic diff;
2. interface diffs that were dependent on assertion ordering because parallel
   assertions were collapsed into a single dictionary entry;
3. a consumer binding whose semantic identity did not encode the resolved
   producer contract even though AE-25 reasoning could distinguish producer
   contract versions;
4. candidate assertions participating in the main semantic fingerprint even
   though they were explicitly quarantined by AE-24/AE-25.

The corrective implementation resolves these inconsistencies using a single
canonical semantic representation.

## Compatibility

AE-24 contract admission remains the input boundary and is unchanged.

AE-25 symbolic reasoning remains the reasoning authority for its existing
rules and is not replaced by AE-26.

The AE-26 semantic vocabulary schema is `v2`. The evolution report is
versioned to `v3` because it now exposes an explicit `semantic_diff_fingerprint`
that separates semantic determinism from exact contract/report identity. Existing v1 serialized
AE-26 outputs should not be silently interpreted as v2 outputs.

## Security and budgets

AE-24 continues to enforce contract, source, graph, and assertion budgets.
AE-26 retains a 12,000-change evolution budget.

The CLI reuses AE-25's bounded canonical contract/evidence loader and uses a
bounded regular-file reader for serialized verification claims.

Source programs are never executed.

Symlink evidence paths remain forbidden.

## Authority boundary

A source digest establishes consistency between a contract and supplied bytes.
It does not authenticate the source producer or prove the truth of an
assertion.

A semantic fingerprint establishes deterministic identity under this
vocabulary. It is not a proof of real-world correctness.

Candidate/model output is never promoted automatically.


## Diff identity boundary

Assertion ordering can change the exact admitted contract digest without
changing the semantic state. This is intentional: `contract_sha256` is a
source/contract identity, while `semantic_diff_fingerprint` is the deterministic
identity of the derived semantic evolution result. The complete
`report_sha256` remains an integrity seal over the entire report.

The test suite therefore compares semantic fields, reported changes, status,
authority, and `semantic_diff_fingerprint` for order-independence tests. It
also explicitly verifies that the exact contract and report digests may differ
under reordered assertions.

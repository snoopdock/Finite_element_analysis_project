# ADR-059: Verifier Authority Preservation During Re-verification

## Status
Accepted

## Decision
G3.3.2 preserves `requested_verifier_ids` when a historical verification obligation is rebased. The integration layer does not infer that a cheaper, newer, or similarly capable verifier is semantically equivalent to the originally authorized verifier.

Verifier substitution requires a future explicit equivalence/substitution contract.

## Consequences
Cost-aware orchestration may allocate scarce budget across impacted obligations, but it cannot broaden semantic verification authority merely to obtain a cheaper route or additional fallback.

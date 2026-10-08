
# ADR-037: Separate Evidence State from Verification Decision

## Status
Accepted for G3.1.0.

## Context
A single boolean or overloaded `verified` flag cannot distinguish evidence maturity from the outcome of a verification obligation. For example, evidence may be validated while the tested hypothesis is refuted.

## Decision
Two orthogonal vocabularies are used.

Evidence lifecycle / epistemic state:

- `proposed`
- `observed`
- `corroborated`
- `validated`
- `rejected`
- `inconclusive`
- `stale`

Verification decision:

- `confirmed`
- `refuted`
- `inconclusive`
- `error`

A graph edge discovered by traversal defaults to `observed`. Corroboration requires explicit independent provenance. `validated` requires execution of an explicit verifier. Verification decisions do not themselves define policy severity.

## Consequences
The system can represent uncertainty and disagreement without pretending that every verification run yields truth. Rule eligibility can require a minimum evidence state independently of the verification decision that triggers the rule.

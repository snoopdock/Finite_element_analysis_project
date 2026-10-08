# ADR-052: Cost-Aware Verification Orchestration Boundary

## Status

Accepted for G3.3.0.

## Context

G3.1 introduced explicit verification obligations and immutable receipts. G3.2 added change-aware re-verification planning and deterministic replay. The repository now needs to decide which verifier to run, in what order, and under what resource envelope without turning operational scheduling into semantic judgment.

The neurosymbolic auditing literature treats auditing as iterative evidence seeking: inexpensive semantic operations should narrow the search space before more expensive analyses are invoked. That pattern is useful here, but only if cost and audit truth remain separate concepts.

## Decision

Introduce a dedicated orchestration layer above the verifier registry and verification service.

The orchestration layer may:

- enumerate compatible registered verifiers;
- apply explicit resource profiles;
- reserve a bounded verification route;
- order work by operational priority;
- execute only actions present in the sealed plan;
- stop when a terminal verification receipt satisfies the requested evidence state.

The orchestration layer may not:

- create audit findings;
- mutate finding lifecycle;
- alter canonical semantic graph state;
- persist long-term audit memory;
- convert cost, priority, or route order into confidence or truth.

## Consequences

Verification policy remains independently testable. Future solver, executable, and external verifiers can be introduced without changing the semantic meaning of existing receipts. Resource decisions become reproducible artifacts instead of hidden control flow.

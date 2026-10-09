# ADR-061: Controlled High-Assurance Verification Boundary

## Status
Accepted

## Decision
High-assurance verification is implemented behind a dedicated adapter registry and controlled executor. Only explicitly registered adapters may run. The executor does not expose arbitrary shell, network, graph mutation, finding creation, promotion, or memory-persistence authority.

High assurance means stronger, bounded evidence under a declared validation envelope; it does not mean globally correct, complete, or infallible.

## Consequences
Static analysis, solver, executable-witness, and theorem-prover mechanisms can evolve independently while preserving one audit contract. New mechanisms require explicit adapters and policy activation.

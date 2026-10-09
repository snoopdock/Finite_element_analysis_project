# ADR-063: No Implicit Formal Solver Activation

## Status
Accepted

## Decision
The repository's placeholder SAT/SMT/CP-SAT/Lean formal layer remains inactive in G3.4.0. Solver or theorem-prover verification may not be advertised merely because placeholder modules exist.

Activation requires a real adapter with containment semantics, versioned tool identity, certificate/witness handling, validation-envelope semantics, deterministic or explicitly characterized execution behavior, and dedicated tests.

## Consequences
G3.4.0 ships two real deterministic read-only mechanisms—Python AST static-import verification and SHA-256 artifact-integrity verification—without overclaiming formal-verification capability.

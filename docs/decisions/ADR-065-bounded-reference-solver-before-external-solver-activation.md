# ADR-065 — Bounded Reference Solver Before External Solver Activation

## Status
Accepted for G3.4.1.

## Decision
The first active solver path is a deterministic, in-process, exhaustive Boolean CNF solver bounded to at most 12 variables. Existing `formal/sat`, `formal/smt`, `formal/cpsat`, and Lean placeholders remain inactive.

## Rationale
A small reference solver lets the repository validate obligation routing, solver witnesses, validation envelopes, explicit activation, and orchestration integration without falsely claiming production SAT/SMT/theorem-proving capability.

## Evidence semantics
For accepted CNF instances, truth-assignment enumeration is exhaustive within the declared propositional scope. SAT returns a concrete satisfying assignment. UNSAT records exhaustive assignment-space traversal. Neither result generalizes to SMT theories, first-order logic, optimization, or larger instances.

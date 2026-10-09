# ADR-068 — Independent Certificate Validation Before Evidence Promotion

## Status
Accepted for G3.4.2.

## Context
An external solver can report `SAT`, `UNSAT`, or `UNKNOWN`, but allowing the producer to choose its own evidence state would collapse the distinction between candidate evidence and verified knowledge.

## Decision
External solver output is never sufficient, by itself, to produce `VALIDATED` evidence.

For the initial CNF pathway:

- a SAT result reaches `VALIDATED` only when repository-owned code independently checks that the supplied model binds every declared variable and satisfies every clause;
- an UNSAT result reaches `VALIDATED` only when repository-owned code can independently discharge the claim within its configured bounded enumeration envelope;
- an unsupported large UNSAT claim remains `OBSERVED` and `PARTIAL`, even when the process exits successfully and the protocol response is well formed;
- if independent checking finds a satisfying model that contradicts external UNSAT, that counterexample is preserved as validated evidence and the external claim is overruled.

`certificate_complete_within_scope` is introduced for proofs/witnesses that completely discharge the declared claim without replaying the producer's full search.

## Consequences
Evidence promotion depends on the verifier that checks the certificate, not on the solver that emitted it. Future DRAT/LRAT/SMT-proof/Lean certificate checkers may extend the supported proof formats without changing this boundary.

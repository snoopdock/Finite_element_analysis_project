# ADR-070 — Proof-Carrying UNSAT Requires a Repository-Owned Checker

## Status
Accepted for G3.4.3.

## Context
G3.4.2 intentionally prevented an external solver from promoting its own UNSAT verdict to `VALIDATED` unless the repository could independently re-establish the result by bounded exhaustive enumeration. That boundary is correct, but bounded enumeration does not scale to larger CNF instances.

A scalable negative-result path therefore requires proof-carrying solver output: the solver may produce a proof, but proof validity must be decided by code owned by the repository rather than by the producing solver.

## Decision
An external UNSAT result may reach `VALIDATED` through a proof certificate only when all of the following hold:

1. the certificate is bound to the exact normalized CNF digest;
2. the certificate declares an explicitly supported proof format;
3. a repository-owned proof checker is registered for that format;
4. the checker validates every inference required by the supported proof system;
5. the proof establishes the terminal UNSAT claim within configured resource limits;
6. the resulting validation envelope records the proof format, checker identity/version, proof digest, and declared scope.

The external solver process never selects the evidence state. Unsupported, malformed, invalid, or resource-exhausted proofs do not become validated evidence merely because the solver returned `UNSAT`.

## Consequences
Proof formats become explicit semantic capabilities rather than parser conveniences. Future DRAT, LRAT, SMT proof, or theorem-prover adapters must add real repository-owned checkers (or a separately trusted checker boundary) before their negative results can gain validated status.

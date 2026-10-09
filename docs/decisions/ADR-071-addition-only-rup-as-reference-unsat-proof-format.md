# ADR-071 — Addition-Only RUP as the Reference UNSAT Proof Format

## Status
Accepted for G3.4.3.

## Context
The repository needs one real proof-carrying negative certificate to validate the architecture end-to-end. Implementing full DRAT/LRAT support at this stage would add significant parser and inference complexity before the proof-checker boundary itself has been exercised.

## Decision
G3.4.3 supports `cnf-rup/v1`, an intentionally narrow addition-only reverse-unit-propagation proof format.

For each proof clause `C`, the checker verifies that unit propagation on the current CNF plus the negation of every literal in `C` reaches contradiction. Accepted clauses are appended to the working formula. The final proof step must be the empty clause.

The initial format does **not** support:

- clause deletion;
- RAT inference;
- DRAT extensions;
- LRAT hint chains;
- SMT theory lemmas;
- proof steps referring to variables outside the declared CNF.

A valid RUP proof is a complete certificate of UNSAT for the exact bound CNF and therefore yields `certificate_complete_within_scope`.

## Consequences
The checker is small enough to audit directly and strong enough to validate nontrivial UNSAT proofs without replaying the solver's search. The narrow proof language is a feature: unsupported proof operations are rejected rather than approximately interpreted.

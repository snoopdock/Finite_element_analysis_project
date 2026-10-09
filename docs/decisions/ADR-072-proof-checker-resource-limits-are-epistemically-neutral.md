# ADR-072 — Proof-Checker Resource Limits Are Epistemically Neutral

## Status
Accepted for G3.4.3.

## Context
Proof certificates arrive from an external process and are therefore untrusted input. Even a sound proof format can be used to create excessive CPU or memory work if parsing and checking are unbounded.

## Decision
Every repository-owned UNSAT proof checker must enforce explicit deterministic resource limits. The initial RUP checker bounds:

- proof step count;
- total proof literal count;
- individual clause width.

Exceeding a proof-checking resource limit is an operational inability to validate that certificate. It is **not** evidence that the CNF is satisfiable and must not be converted into `REFUTED`, `REJECTED` semantic truth, or a finding.

Where a separate independent verification mechanism is available (for example bounded exhaustive enumeration), that mechanism may still establish the verdict. Otherwise the external UNSAT result remains only an observation with partial completeness.

## Consequences
Adversarial proof size is bounded without conflating execution budget with semantics. Future proof checkers must expose their own limits in their validation envelopes and witnesses.

# ADR-078 — Proof Retrieval and Resource Failure Are Epistemically Neutral

**Status:** Accepted  
**Milestone:** G3.4.5

## Context

A detached proof introduces operational failure modes that do not exist for a small inline certificate: missing stores, missing artifacts, digest mismatch, size mismatch, malformed JSONL, line-size limits, artifact-size limits, proof-step limits, and formula/RAT resource limits.

Treating any of these failures as evidence against the claimed theorem would confuse infrastructure state with semantics.

## Decision

Failure to retrieve, integrity-check, parse, or completely check a detached proof means only:

> the detached proof was not accepted under the current validation envelope.

For a large external UNSAT claim this remains `OBSERVED/PARTIAL`. It does not establish SAT, refute UNSAT, mutate a finding, or promote candidate knowledge. If the CNF is small enough, an independent repository-owned bounded enumeration path may still establish SAT or UNSAT without relying on the detached proof.

## Consequences

- Operational availability cannot silently become scientific truth.
- Resource limits remain policy/engineering controls rather than logical axioms.
- Audit reports can distinguish "proof unavailable/uncheckable" from "proof checked and invalid" and from "counterexample independently found".

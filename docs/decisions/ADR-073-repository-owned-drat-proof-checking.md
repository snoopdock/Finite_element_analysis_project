# ADR-073 — Repository-Owned DRAT Proof Checking

## Status
Accepted — G3.4.4.

## Decision
The semantic-audit repository may promote an external Boolean-CNF UNSAT claim to validated evidence when a repository-owned checker independently accepts a proof in the controlled `cnf-drat/v1` format.

The reference checker implements clause addition by RUP or RAT. RAT uses the **first literal of the added clause as the pivot** and requires every non-tautological resolvent against an active clause containing the opposite pivot literal to be RUP. A proof succeeds only when its final operation adds the empty clause.

## Boundary
The external solver remains an evidence producer. It cannot select the checker, alter checker rules, or assign evidence state. DRAT checking imports neither the placeholder `formal` package nor subprocess execution.

## Consequences
DRAT provides a broader negative-certificate path than addition-only RUP while keeping the checking algorithm repository-owned and auditable. Native DRAT text parsing, LRAT hints, and high-performance watched-literal implementations are deferred.

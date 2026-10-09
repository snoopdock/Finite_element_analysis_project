# ADR-064 — Explicit Activation for Sensitive High-Assurance Adapters

## Status
Accepted for G3.4.1.

## Decision
Solver, executable-witness, and theorem-prover mechanisms require two independent permissions before execution: the mechanism must be allowed by policy and the concrete adapter identifier must be explicitly activated.

Registration, package installation, importability, and presence in the orchestration profile catalog are **not activation**.

## Rationale
High-assurance mechanisms may carry materially different execution and trust boundaries. Treating capability discovery as execution authority would allow an installed solver or executable harness to become active accidentally.

## Consequences
The default G3.4 policy continues to run only static-analysis and artifact-integrity adapters. G3.4.1's bounded CNF solver and executable-witness adapter remain denied unless a caller constructs a policy that both permits their mechanism and names their adapter ID in `activated_adapter_ids`.

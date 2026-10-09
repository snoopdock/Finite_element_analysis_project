# ADR-055: Adaptive Verification Replanning Boundary

## Status
Accepted

## Decision
Adaptive orchestration may react only to explicit prior execution outcomes and may select only registered, profiled, policy-eligible verifiers. A new verifier must appear in an immutable continuation plan before execution.

## Consequences
Adaptive behavior is outcome-driven but not self-authorizing. Verifier output remains evidence data, not an instruction stream. Findings, canonical graph mutation, promotion, and audit-memory persistence remain outside the replanning layer.

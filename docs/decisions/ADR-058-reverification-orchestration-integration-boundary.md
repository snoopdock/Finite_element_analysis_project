# ADR-058: Re-verification / Orchestration Integration Boundary

## Status
Accepted

## Decision
G3.2 incremental re-verification and G3.3 audit orchestration are composed through a separate `semantic_audit.integration` layer. Neither core layer may depend back on the integration package.

The bridge may replay explicit prior analysis/obligation intent against an after-snapshot and translate eligible receipt re-verification tasks into orchestration objectives. It may not create findings, mutate canonical graph state, or silently persist memory.

## Consequences
The repository gains budget-aware incremental receipt verification without collapsing graph evolution, verification, and orchestration into one authority. Cross-layer coupling remains explicit and testable.

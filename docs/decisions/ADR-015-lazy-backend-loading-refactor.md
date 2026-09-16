# ADR-015: Lazy Backend Loading Refactor

## Status
Accepted for G2.5 Step 11B

## Decision

BackendFactory will load backend adapters only when requested.

This prevents unnecessary dependency coupling.

Architecture:

BackendFactory
 |
 +-- request: networkx -> import NetworkXAdapter
 |
 +-- request: scipy -> import SciPyAdapter

Benefits:
- optional backend dependencies
- cleaner universal semantic graph architecture
- easier future backend expansion

The adapter contract, capability registry, and selection policy remain unchanged.

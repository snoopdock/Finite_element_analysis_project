# ADR --- First Implementation Phase

## Status

Accepted

## Context

The architecture is complete and implementation must begin.

Large-scale modification creates unnecessary risk.

------------------------------------------------------------------------

# Decision

Implement in small validated phases.

------------------------------------------------------------------------

# Reasons

This approach provides:

-   controlled migration;
-   easier debugging;
-   preservation of existing functionality.

------------------------------------------------------------------------

# Consequence

The initial codebase may temporarily contain adapters and parallel
representations. This is acceptable during migration.

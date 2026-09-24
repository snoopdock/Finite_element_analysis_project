# ADR --- First Repository Modifications

## Status

Accepted

## Context

The repository already contains working components.

A large refactor introduces unnecessary risk.

------------------------------------------------------------------------

# Decision

Use adapter-based incremental migration.

------------------------------------------------------------------------

# Benefits

-   preserves current behavior;
-   enables testing;
-   reduces migration risk.

------------------------------------------------------------------------

# Constraint

No implementation should violate L1-L23-L ownership boundaries.

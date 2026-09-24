# ADR --- Prototype Integration Strategy

## Status

Accepted

## Context

The repository already contains working components.

A direct replacement approach creates unnecessary risk.

------------------------------------------------------------------------

# Decision

Integrate through adapters and incremental migration.

------------------------------------------------------------------------

# Reasons

This preserves:

-   existing functionality;
-   previous engineering work;
-   test stability.

------------------------------------------------------------------------

# Consequence

The repository may temporarily contain both old and new representations.

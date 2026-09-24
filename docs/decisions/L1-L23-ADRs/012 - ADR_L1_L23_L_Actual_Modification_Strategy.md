# ADR --- Actual Repository Modification Strategy

## Status

Accepted

## Context

The repository already contains functional components.

Large changes risk architectural regression.

------------------------------------------------------------------------

# Decision

Use incremental modification with adapters and tests.

------------------------------------------------------------------------

# Principles

-   preserve existing behavior;
-   introduce boundaries gradually;
-   document every transition.

------------------------------------------------------------------------

# Consequence

The migration may temporarily contain compatibility layers. This is
acceptable.

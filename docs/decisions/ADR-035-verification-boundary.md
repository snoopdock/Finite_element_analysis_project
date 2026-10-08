# ADR-035: Verification Boundary

## Status

Accepted

## Decision

Graph analysis produces observations only.

Verification and audit decisions exist outside the graph layer.

## Rationale

This prevents coupling semantic representation with policy judgment.

Architecture:

    Graph
     |
    Observation
     |
    Verification
     |
    Finding

## Consequences

Positive:

-   reproducibility;
-   extensibility;
-   independent rule evolution.

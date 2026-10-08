# ADR-036: Evidence State Machine

## Decision

Evidence lifecycle uses explicit states:

-   proposed;
-   observed;
-   corroborated;
-   validated;
-   rejected;
-   stale.

## Rationale

Binary truth states are insufficient for scientific auditing.

## Consequence

Every conclusion must have a traceable evidence history.

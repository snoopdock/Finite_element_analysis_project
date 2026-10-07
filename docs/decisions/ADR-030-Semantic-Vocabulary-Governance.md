# ADR-030 --- Semantic Vocabulary Governance

## Status

Accepted

## Context

Large autonomous repositories are vulnerable to semantic drift when
common terms acquire multiple meanings.

## Decision

Important repository concepts SHALL have controlled vocabulary
definitions.

Each term requires:

-   definition;
-   owning domain;
-   allowed relationships;
-   forbidden interpretations.

## Examples

### Evidence

Allowed:

    Evidence Artifact

    Evidence Relationship

Forbidden:

    Evidence = Any Citation

### Graph Node

Allowed:

    Computational Representation

Forbidden:

    Graph Node = Semantic Entity

## Consequences

Terminology becomes machine-auditable.

Architectural meaning becomes explicit rather than relying on developer
memory.

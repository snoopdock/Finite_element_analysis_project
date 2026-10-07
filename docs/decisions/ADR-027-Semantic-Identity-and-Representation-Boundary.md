# ADR-027 --- Semantic Identity and Representation Boundary

## Status

Accepted

## Context

The semantic graph architecture requires stable meaning across changing
computational representations.

A graph node, JSON object, database record, or visualization element is
a representation. It is not the semantic entity itself.

Without an explicit boundary, semantic drift occurs when representations
gradually acquire domain meaning.

## Decision

The repository SHALL maintain separate identity domains:

-   Artifact Identity
-   Semantic Identity
-   Occurrence Identity
-   Representation Identity
-   Audit Identity

Semantic identity remains independent from graph representation.

## Example

    Semantic Entity:
    section-001

    Representations:
    graph-node-44
    rdf-resource-20
    visualization-node-5

Representations may change while semantic identity remains stable.

## Consequences

Positive:

-   graph backends can change;
-   representations can be regenerated;
-   semantic meaning remains stable.

Negative:

-   additional mapping layers are required.

## Rules

Forbidden:

    Representation Identity == Semantic Identity

Required:

    Representation represents Semantic Entity

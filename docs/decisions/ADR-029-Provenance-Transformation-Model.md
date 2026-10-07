# ADR-029 --- Provenance Transformation Model

## Status

Accepted

## Context

Autonomous systems require the ability to reconstruct how artifacts and
semantic objects were created.

Identity alone cannot answer historical questions.

## Decision

Meaningful transformations SHALL create explicit transformation events.

## Core Model

    Input Object

    ↓

    Transformation Event

    ↓

    Output Object

## Transformation Event Contains

-   operation
-   inputs
-   outputs
-   responsible agent
-   version
-   timestamp

## Examples

    PDF

    ↓

    Extraction Event

    ↓

    Document Model

    Semantic Objects

    ↓

    Graph Build Event

    ↓

    Semantic Graph

## Consequences

The repository can answer:

-   Where did this object come from?
-   What created this finding?
-   What changed between versions?

## Rules

Derived objects without provenance are invalid semantic artifacts.

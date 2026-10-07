# ADR-032 --- Semantic Graph Computation Backend Boundary

## Status

Accepted

## Context

The repository has established a semantic graph as a representation of
entities and relationships.

Future milestones require graph computation capabilities:

-   traversal;
-   dependency analysis;
-   path discovery;
-   centrality analysis;
-   visualization support.

However, graph computation libraries and semantic representation have
different responsibilities.

A computational graph library optimizes for algorithms.

The semantic graph optimizes for meaning preservation.

Combining them directly would create architectural coupling and risk
making a third-party library the owner of semantic meaning.

------------------------------------------------------------------------

# Decision

The repository SHALL maintain a strict separation between:

    Semantic Graph Model

    and

    Graph Computation Backend

The semantic graph remains the source of truth.

Graph libraries are replaceable computation adapters.

------------------------------------------------------------------------

# Architecture

``` mermaid
flowchart LR

A[Semantic Graph]

B[Computation Adapter]

C[Graph Backend]

D[Analysis Results]


A --> B

B --> C

C --> D
```

------------------------------------------------------------------------

# Responsibilities

## Semantic Graph Layer

Responsible for:

-   semantic entities;
-   semantic relationships;
-   identity references;
-   provenance links;
-   domain meaning.

The semantic graph defines:

    What exists

------------------------------------------------------------------------

## Computation Backend Layer

Responsible for:

-   graph traversal;
-   algorithms;
-   optimization;
-   numerical analysis.

The computation backend defines:

    How relationships are computed

------------------------------------------------------------------------

# Backend Independence

The architecture SHALL support multiple future backends:

Possible examples:

-   NetworkX;
-   igraph;
-   graph-tool;
-   SNAP;
-   custom implementations.

Changing the backend must not require changing:

-   semantic identities;
-   semantic relationships;
-   provenance;
-   audit contracts.

------------------------------------------------------------------------

# Forbidden Architecture

The following design is prohibited:

    Semantic Meaning

    inside

    NetworkX Node Attributes

or:

    NetworkX Graph

    as

    the Semantic Source of Truth

------------------------------------------------------------------------

# Required Architecture

The correct relationship is:

    Semantic Graph

    ↓

    Adapter

    ↓

    Computation Backend

    ↓

    Analysis Result

------------------------------------------------------------------------

# Consequences

## Positive Consequences

The repository gains:

-   backend flexibility;
-   long-term maintainability;
-   separation of concerns;
-   easier testing;
-   safer evolution.

------------------------------------------------------------------------

## Negative Consequences

The repository requires:

-   adapter code;
-   conversion layers;
-   additional interfaces.

This cost is accepted because semantic stability is more important than
short-term implementation simplicity.

------------------------------------------------------------------------

# Relationship With G2.75

This ADR depends on previous architectural decisions:

## ADR-027 --- Identity Boundary

The computation backend cannot own semantic identity.

## ADR-029 --- Provenance Model

Analysis results must preserve traceability.

## ADR-031 --- Semantic Audit Architecture

Graph analysis feeds auditing but does not replace semantic rules.

------------------------------------------------------------------------

# G3 Scope Enabled By This ADR

The following capabilities may now be implemented:

## Structural Analysis

Examples:

    Find connected components

    Find neighbors

    Traverse dependency paths

------------------------------------------------------------------------

## Dependency Analysis

Examples:

    What modules depend on this artifact?

    What semantic objects are affected by a change?

------------------------------------------------------------------------

## Path Analysis

Examples:

    Find path from claim to evidence

    Find path from finding to source artifact

------------------------------------------------------------------------

## Visualization

Examples:

    Generate graph views

    Display dependency structures

------------------------------------------------------------------------

# Explicitly Deferred

This ADR does not authorize:

-   ontology reasoning;
-   scientific truth inference;
-   automatic correction;
-   autonomous decision making.

Those belong to later reasoning milestones.

------------------------------------------------------------------------

# Validation Requirements

Implementation must verify:

## Test 1

Semantic graph behavior remains independent from backend choice.

## Test 2

Backend replacement does not change semantic output.

## Test 3

Analysis results retain provenance references.

## Test 4

No semantic identity is created inside the computation backend.

------------------------------------------------------------------------

# Final Statement

ADR-032 establishes that graph computation is an implementation
capability, not a semantic authority.

The semantic graph remains the stable foundation.

Computational backends remain replaceable tools.

This boundary enables G3 graph reasoning while preserving the
architectural integrity established in G2.75.

# ADR-035 --- Graph Visualization Boundary

## Status

Accepted

## Context

The semantic graph requires visualization capabilities for:

-   debugging;
-   architecture exploration;
-   audit explanation;
-   human understanding of complex relationships.

However, visualization introduces a new representation layer.

A visual node is not the same thing as a semantic entity.

A displayed edge is not automatically a semantic relationship.

Without an explicit boundary, users and future systems may begin
treating visual representations as authoritative semantic objects.

------------------------------------------------------------------------

# Decision

The repository SHALL treat visualization as a projection layer.

Visualization is a consumer of semantic information.

It does not own:

-   identity;
-   meaning;
-   provenance;
-   semantic relationships.

------------------------------------------------------------------------

# Architecture

``` mermaid
flowchart LR

A[Semantic Graph]

B[Visualization Projection]

C[Visual Representation]

D[Human/User Interaction]


A --> B

B --> C

C --> D
```

------------------------------------------------------------------------

# Responsibilities

## Semantic Graph Layer

Owns:

-   semantic identities;
-   relationships;
-   attributes;
-   provenance;
-   domain meaning.

------------------------------------------------------------------------

## Visualization Layer

Owns:

-   layout;
-   colors;
-   grouping;
-   display configuration;
-   interaction state.

------------------------------------------------------------------------

# Identity Boundary

A visual element must reference a semantic identity.

Example:

    Semantic Entity:

    section-001


    Visual Node:

    display-node-55
    represents:
    section-001

The visual node is replaceable.

The semantic identity is not.

------------------------------------------------------------------------

# Forbidden Architecture

The following designs are prohibited:

    Visual Node ID == Semantic Identity

or:

    User-edited visualization

    ↓

    Changes semantic meaning directly

------------------------------------------------------------------------

# Required Projection Model

The correct flow:

    Semantic Object

    ↓

    Visualization Projection

    ↓

    Visual Object

A visualization is a view of meaning, not the owner of meaning.

------------------------------------------------------------------------

# Visualization and Provenance

Visualization artifacts may have provenance.

Example:

    Visualization Artifact

    created by:

    GraphVisualizer v1.0

    from:

    semantic_graph_snapshot_001

However, visualization provenance is separate from semantic provenance.

------------------------------------------------------------------------

# Interaction With Audit Engine

Visualization can support audit explanation.

Example:

    Finding

    ↓

    Provenance Chain

    ↓

    Graph Path

    ↓

    Visualization

The visualization helps humans understand the result.

It does not generate the finding.

------------------------------------------------------------------------

# Interactive Exploration

Future interactive tools may allow:

-   filtering;
-   expanding subgraphs;
-   selecting nodes;
-   inspecting relationships.

These actions must remain projections.

Example:

Allowed:

    Hide unrelated nodes

Forbidden:

    Delete hidden nodes from semantic graph

------------------------------------------------------------------------

# Relationship With Graph Analysis

Visualization consumes analysis results.

Example:

    Centrality Analysis

    ↓

    Highlighted Nodes

    ↓

    Visualization

The highlighted display does not mean:

    Important Node = Important Concept

unless a semantic rule explicitly establishes that interpretation.

------------------------------------------------------------------------

# Consequences

## Positive

The repository gains:

-   safe graph exploration;
-   explainable audits;
-   replaceable visualization tools;
-   preservation of semantic integrity.

------------------------------------------------------------------------

## Negative

Additional mapping between semantic objects and visual objects is
required.

This cost is accepted.

------------------------------------------------------------------------

# Validation Requirements

Implementation SHALL verify:

## Test 1

Visual identifiers cannot replace semantic identifiers.

## Test 2

Visualization changes do not mutate semantic meaning.

## Test 3

Displayed relationships correspond to existing semantic relationships.

## Test 4

Visualization artifacts retain references to their source graph state.

------------------------------------------------------------------------

# Relationship With Previous ADRs

Depends on:

## ADR-027

Identity remains separate from representation.

## ADR-032

Computation backends are not semantic authorities.

## ADR-033

Queries provide controlled access to graph information.

## ADR-034

Analysis results require semantic interpretation.

------------------------------------------------------------------------

# Final Statement

ADR-035 establishes visualization as a projection layer.

The visualization system makes semantic structures understandable to
humans, but it does not define what those structures mean.

The architectural chain remains:

    Semantic Graph

    ↓

    Analysis

    ↓

    Visualization

    ↓

    Human Understanding

Meaning flows from the semantic model outward.

It never flows backward from the display into the semantic model.

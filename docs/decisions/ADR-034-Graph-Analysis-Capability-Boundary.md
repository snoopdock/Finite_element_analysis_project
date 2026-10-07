# ADR-034 --- Graph Analysis Capability Boundary

## Status

Accepted

## Context

The semantic graph foundation provides a stable representation of
entities, relationships, identities, and provenance.

G3 introduces computational graph analysis.

However, graph algorithms must remain separated from semantic
interpretation.

A graph algorithm can determine:

    There is a path between A and B

but it cannot determine:

    The relationship between A and B is scientifically meaningful

That distinction is essential for an autonomous reasoning system.

------------------------------------------------------------------------

# Decision

The repository SHALL define a strict boundary between:

    Graph Analysis

    and

    Semantic Reasoning

Graph analysis provides computational observations.

Semantic reasoning determines meaning.

------------------------------------------------------------------------

# Architecture

``` mermaid
flowchart LR

A[Semantic Graph]

B[Graph Analysis Layer]

C[Analysis Results]

D[Semantic Rule Engine]

E[Audit Findings]


A --> B

B --> C

C --> D

D --> E
```

------------------------------------------------------------------------

# Graph Analysis Responsibilities

The graph analysis layer SHALL provide:

-   traversal;
-   path discovery;
-   dependency analysis;
-   connected component analysis;
-   subgraph extraction;
-   centrality calculations;
-   structural metrics.

These operations describe graph structure.

------------------------------------------------------------------------

# 1. Traversal Analysis

Purpose:

Discover reachable entities.

Examples:

    Which nodes are connected to this artifact?

    Which dependencies exist downstream?

Output:

    Graph Observation

Not:

    Semantic Conclusion

------------------------------------------------------------------------

# 2. Path Analysis

Purpose:

Discover relationship chains.

Example:

    Finding

    ↓

    Claim

    ↓

    Evidence

    ↓

    Source Artifact

The existence of a path does not automatically prove validity.

A rule engine must evaluate the meaning of the path.

------------------------------------------------------------------------

# 3. Dependency Analysis

Purpose:

Understand impact relationships.

Examples:

    What objects depend on this document?

    Which components may be affected by this change?

This enables:

-   impact prediction;
-   regression analysis;
-   change planning.

------------------------------------------------------------------------

# 4. Connected Components

Purpose:

Identify graph regions.

Examples:

    Independent modules

    Separate document regions

    Disconnected knowledge areas

A connected component does not automatically represent a semantic
domain.

------------------------------------------------------------------------

# 5. Centrality Analysis

Purpose:

Identify structurally important nodes.

Examples:

-   high dependency nodes;
-   highly connected entities;
-   frequently referenced objects.

Important:

Centrality is structural importance.

It is not:

-   scientific importance;
-   truth;
-   priority.

------------------------------------------------------------------------

# Forbidden Interpretations

The following mappings are prohibited:

    High Centrality = Important Scientific Concept

    Shortest Path = Correct Reasoning Path

    Graph Density = Knowledge Quality

    Many Connections = Truth

These require semantic evaluation.

------------------------------------------------------------------------

# Relationship With Semantic Audit Engine

Graph analysis provides evidence for auditing.

Example:

Graph result:

    Component A depends on Component B

The rule engine evaluates:

    Is this dependency allowed?

------------------------------------------------------------------------

Architecture:

``` mermaid
flowchart TB

GraphAnalysis

Observation

SemanticRule

Finding


GraphAnalysis --> Observation

Observation --> SemanticRule

SemanticRule --> Finding
```

------------------------------------------------------------------------

# Relationship With Provenance

Every analysis result that contributes to auditing SHALL preserve:

-   input graph state;
-   query parameters;
-   algorithm used;
-   execution context.

Example:

    Centrality Result

    created by:

    PageRank Analysis v1

    on:

    semantic_graph_2026_10_07

------------------------------------------------------------------------

# Deferred Capabilities

This ADR explicitly does NOT authorize:

## Ontology Reasoning

Example:

    Concept A is a subtype of Concept B

------------------------------------------------------------------------

## Scientific Inference

Example:

    Evidence supports hypothesis

------------------------------------------------------------------------

## Autonomous Repair

Example:

    Modify code to fix violation

------------------------------------------------------------------------

## Truth Evaluation

Example:

    Claim is correct

These require additional reasoning layers.

------------------------------------------------------------------------

# Implementation Boundary

Recommended architecture:

    semantic/

    graph/

        core/

        adapters/

        queries/

        analysis/

        results/

    reasoning/

        rules/

        evaluation/

------------------------------------------------------------------------

# Validation Requirements

Implementation SHALL verify:

## Test 1

Graph analysis does not modify semantic identities.

## Test 2

Analysis results preserve provenance.

## Test 3

Algorithms remain replaceable.

## Test 4

No graph metric is interpreted as semantic truth.

------------------------------------------------------------------------

# Consequences

## Positive

The repository gains:

-   reusable graph computation;
-   safe reasoning foundations;
-   backend independence;
-   explainable analysis.

## Negative

A separate reasoning layer must be implemented.

This is intentional.

------------------------------------------------------------------------

# Relationship With Previous ADRs

Depends on:

## ADR-027

Identity remains separate from representation.

## ADR-031

Semantic audit evaluates meaning.

## ADR-032

Computation backends remain replaceable.

## ADR-033

Queries provide controlled access.

------------------------------------------------------------------------

# Final Statement

ADR-034 establishes that graph analysis is an observation-producing
capability.

It provides structural knowledge.

It does not provide semantic conclusions.

This boundary allows G3 to introduce powerful graph algorithms while
preserving the semantic integrity architecture established in G2.75.

# ADR-033 --- Graph Query Architecture

## Status

Accepted

## Context

The semantic graph established in previous milestones provides a
representation of entities and relationships.

G3 introduces graph analysis capabilities. However, graph access must
remain controlled.

Allowing every subsystem to directly traverse graph structures would
create:

-   duplicated logic;
-   inconsistent interpretation;
-   hidden dependencies;
-   violation of semantic boundaries.

A dedicated query architecture is therefore required.

------------------------------------------------------------------------

# Decision

The repository SHALL provide a semantic graph query layer between
consumers and graph computation backends.

The query layer is responsible for expressing meaningful questions about
the semantic graph.

------------------------------------------------------------------------

# Architecture

``` mermaid
flowchart LR

A[Semantic Graph]

B[Query Layer]

C[Graph Backend]

D[Analysis Result]


A --> B

B --> C

C --> D
```

------------------------------------------------------------------------

# Query Layer Responsibilities

The query layer SHALL:

-   provide stable graph access interfaces;
-   translate semantic questions into graph operations;
-   preserve identity and provenance;
-   prevent consumers from depending directly on backend
    implementations.

------------------------------------------------------------------------

# Query Categories

## 1. Structural Queries

Purpose:

Understand graph structure.

Examples:

    Which nodes are connected?

    What relationships exist between two entities?

    What are the neighbors of this entity?

Possible operations:

-   neighbor lookup;
-   relationship filtering;
-   subgraph extraction.

------------------------------------------------------------------------

## 2. Dependency Queries

Purpose:

Understand impact relationships.

Examples:

    What depends on this artifact?

    Which modules are affected by this change?

    Which semantic objects originate from this document?

These queries support:

-   impact analysis;
-   regression detection;
-   change planning.

------------------------------------------------------------------------

## 3. Path Queries

Purpose:

Discover semantic chains.

Examples:

    Find path from claim to evidence.

    Find path from audit finding to source artifact.

Example:

    Finding

    ↓

    Audit Rule

    ↓

    Claim

    ↓

    Evidence Relationship

    ↓

    Source Artifact

------------------------------------------------------------------------

## 4. Provenance Queries

Purpose:

Recover creation history.

Examples:

    Why does this object exist?

    Which transformation created this node?

    What sequence of events produced this finding?

These queries combine:

-   semantic graph;
-   provenance graph.

------------------------------------------------------------------------

# Query API Boundary

Consumers should request semantic operations.

Preferred:

``` python
find_dependency_path(object_id)
```

Not:

``` python
networkx_graph.shortest_path(...)
```

The first preserves architecture.

The second exposes implementation details.

------------------------------------------------------------------------

# Semantic Query Object

Future implementations should use explicit query objects.

Example:

``` python
SemanticQuery(

    query_type="dependency",

    source_identity="artifact-001",

    constraints={}

)
```

The query object should represent intent rather than backend operations.

------------------------------------------------------------------------

# Relationship With NetworkX Adapter

The query layer uses the computation backend indirectly.

Architecture:

``` mermaid
flowchart LR

SemanticIntent

QueryLayer

Adapter

NetworkX

Result


SemanticIntent --> QueryLayer

QueryLayer --> Adapter

Adapter --> NetworkX

NetworkX --> Result
```

NetworkX remains invisible to semantic consumers.

------------------------------------------------------------------------

# Provenance Requirements

Every query result that influences auditing SHALL preserve:

-   source objects;
-   query type;
-   execution context;
-   provenance references.

Example:

A dependency result must explain:

    Why was this dependency discovered?

------------------------------------------------------------------------

# Query Result Model

Conceptual:

``` python
QueryResult(

    objects,

    relationships,

    provenance,

    explanation_context

)
```

------------------------------------------------------------------------

# Forbidden Designs

## Direct backend dependency

Forbidden:

    Audit Engine

    ↓

    NetworkX API

Reason:

The audit layer becomes coupled to a computational library.

------------------------------------------------------------------------

## Uncontrolled graph traversal

Forbidden:

    Any component modifies graph interpretation

Reason:

Meaning becomes distributed.

------------------------------------------------------------------------

# Consequences

## Positive

The repository gains:

-   stable graph interfaces;
-   replaceable computation engines;
-   reusable analysis capabilities;
-   consistent semantic interpretation.

## Negative

Additional abstraction layers are introduced.

This cost is accepted to preserve long-term architectural integrity.

------------------------------------------------------------------------

# G3 Capabilities Enabled

This ADR enables:

-   dependency analysis;
-   semantic path discovery;
-   provenance reconstruction;
-   graph-based auditing;
-   future reasoning engines.

------------------------------------------------------------------------

# Explicitly Deferred

This ADR does not define:

-   scientific truth inference;
-   ontology reasoning;
-   automatic repair;
-   autonomous decision making.

Those belong to later milestones.

------------------------------------------------------------------------

# Validation Requirements

Implementation SHALL verify:

1.  Queries do not require direct backend access.
2.  Results preserve semantic identities.
3.  Provenance information is retained.
4.  Backend replacement does not change query meaning.

------------------------------------------------------------------------

# Final Statement

ADR-033 establishes graph queries as semantic operations rather than raw
graph operations.

The query layer becomes the controlled interface between:

    Semantic Meaning

    and

    Graph Computation

This boundary enables G3 reasoning while preserving the architectural
principles established in G2.75.

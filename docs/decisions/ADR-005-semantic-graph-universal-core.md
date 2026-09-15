# ADR-005: Preserve a Universal Semantic Graph Core

**Status:** Accepted for G2.5  
**Date:** 2026-09-15  
**Decision scope:** Semantic graph architecture  
**Milestone:** G2.5 — Semantic Graph Contract Stabilization

---

## Context

The repository is developing a semantic graph that began as part of the semantic audit engine.

The graph now has two primary near-term uses:

1. code and software review,
2. text, scientific, and document examination.

Both may include LLM-generated semantic extraction.

The graph is also expected to interact with multiple external libraries and representations, including:

- NetworkX,
- SciPy sparse graph representations,
- RDF,
- future OWL reasoning,
- igraph,
- graph-tool,
- SNAP,
- graph databases,
- visualization and numerical-analysis systems.

During G2, the initial NetworkX adapter assumed a different internal graph representation than the current `SemanticGraph`. That exposed an architectural risk: allowing the first backend to dictate the shape of the semantic core.

The current graph core instead uses:

```python
SemanticNode(
    node_id,
    entity_type,
    attributes,
    metadata
)
```

```python
SemanticEdge(
    source_id,
    target_id,
    relation_type,
    attributes,
    metadata
)
```

and:

```python
SemanticGraph(
    nodes: List[SemanticNode],
    edges: List[SemanticEdge]
)
```

The NetworkX adapter was corrected to adapt to the core rather than forcing the core to adopt NetworkX-oriented storage.

---

## Decision

The repository will preserve a universal, library-independent Semantic Graph core.

The Semantic Graph is the authoritative semantic representation.

Backend libraries must adapt to it.

The architecture is:

```text
             Producers
                |
    ---------------------------
    |            |            |
   AST          LLM         LaTeX /
 extraction   extraction    document parsing
    |            |            |
    -------------+-------------
                |
                v
       Universal SemanticGraph
                |
    -----------------------------
    |            |              |
    v            v              v
 NetworkX      SciPy         RDF / OWL
```

No backend is permitted to define the universal graph schema.

---

## Core contract

The core will preserve the following conceptual fields.

### Node

```text
node_id
entity_type
attributes
metadata
```

### Edge

```text
source_id
target_id
relation_type
attributes
metadata
```

The core allows extensible entity and relationship vocabularies.

It does not require every domain to share one closed enumeration of node or relation types.

---

## Domain separation

Code auditing and scientific/text auditing are peer domains.

A software vocabulary may define:

```text
SoftwareModule
Function
Class
IMPORTS
CALLS
DEPENDS_ON
```

A scientific-text vocabulary may define:

```text
ScientificClaim
ResearchPaper
EvidenceItem
SUPPORTED_BY
CONTRADICTS
DERIVED_FROM
```

Neither vocabulary belongs in the universal graph core.

Domain vocabularies may be validated independently.

---

## Backend separation

Adapters may transform the core into backend-native forms.

Examples:

### NetworkX

```text
SemanticGraph -> MultiDiGraph
```

### SciPy

```text
SemanticGraph -> sparse matrix + node-index mapping
```

### RDF

```text
SemanticGraph -> triples / RDF graph
```

Backend adapters are responsible for translating representation while preserving meaning.

---

## Information preservation

Adapters must not silently discard semantic information.

A lossless adapter should preserve:

- node identity,
- entity type,
- relation type,
- edge direction,
- attributes,
- metadata.

Where a backend cannot store all information directly, the adapter must retain side mappings or explicitly declare the projection lossy.

---

## Serialization

The current portable serialization uses:

```text
node_id      -> id
entity_type  -> type

source_id      -> source
target_id      -> target
relation_type  -> relation
```

while preserving:

```text
attributes
metadata
```

The in-memory and serialized field names may differ intentionally.

This distinction must be documented and tested.

---

## Consequences

### Positive

The same graph can support:

- code auditing,
- text examination,
- scientific evidence graphs,
- LaTeX/document structures,
- mixed code-and-evidence graphs,
- numerical graph analysis,
- semantic-web export,
- future ontology reasoning.

Backend replacement does not require redesigning the semantic core.

The repository can use NetworkX where graph algorithms are useful and SciPy where matrix algorithms are more appropriate.

### Costs

Adapters become responsible for additional translation logic.

Some backends require node-index maps or side metadata.

Validation must detect accidental information loss.

Domain vocabularies require separate governance.

These costs are accepted because they preserve semantic stability and avoid backend lock-in.

---

## Rejected alternative: Make the core NetworkX-shaped

An alternative was to change the core so `nodes` became a dictionary because the first NetworkX adapter expected `.values()`.

This was rejected.

Reason:

The adapter assumption was backend-specific and did not justify changing the universal semantic representation.

---

## Rejected alternative: Use NetworkX as the canonical graph

This was rejected because it would:

- couple the audit architecture to one library,
- make SciPy/RDF projections secondary to NetworkX's model,
- blur semantic and computational responsibilities,
- increase migration risk if backend requirements change.

---

## Rejected alternative: Create separate code and text graph cores

This was rejected because both domains need the same fundamental concepts:

```text
entity
identity
typed relationship
attributes
metadata
provenance
```

Separate graph cores would create duplicated infrastructure and semantic drift.

Domain-specific meaning belongs in vocabulary layers, not separate graph foundations.

---

## Rejected alternative: Freeze a global ontology in the core

This was rejected for G2.5.

A universal closed enumeration of all entity and relationship types would prematurely constrain:

- software analysis,
- scientific reasoning,
- document analysis,
- future domains.

Formal ontologies may be layered later.

---

## Compatibility requirement

Future adapters for SciPy, RDF, OWL, graph databases, or other graph libraries must conform to the Semantic Graph Contract.

A new backend must document:

1. how nodes are mapped,
2. how edges are mapped,
3. how identity is preserved,
4. how attributes are preserved,
5. how metadata/provenance is preserved,
6. whether the transformation is lossless,
7. how a reverse mapping can be performed where applicable.

---

## Implementation impact

No immediate change to `semantic_graph.py` is required by this ADR.

The current G2-compatible implementation remains the baseline.

G2.5 should add validation around the contract before introducing additional backend adapters.

---

## Follow-up work

Recommended follow-up items:

- create a machine-readable semantic graph schema,
- add universal contract validation,
- define duplicate-node policy,
- define dangling-edge policy,
- define graph-level schema/version metadata,
- define domain vocabulary packages,
- add SciPy adapter contract,
- add RDF export contract,
- define formal provenance mapping when justified,
- document intentionally lossy transformations.

---

## Final decision

The Semantic Graph is the repository's universal semantic intermediate representation.

The rule is:

> Backends adapt to the Semantic Graph; the Semantic Graph does not reshape itself around backends.

This decision applies to code audit, text/scientific audit, LaTeX/document analysis, numerical graph processing, and future semantic reasoning systems.

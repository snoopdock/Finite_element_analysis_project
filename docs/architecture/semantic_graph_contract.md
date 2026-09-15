# Semantic Graph Contract

**Milestone:** G2.5 — Semantic Graph Contract Stabilization  
**Status:** Draft for architectural freeze  
**Scope:** Universal semantic graph core and backend compatibility  
**Applies to:** code audit, text/scientific audit, document/LaTeX analysis, graph backends, numerical backends, semantic-web exports

---

## 1. Purpose

The Semantic Graph is the repository's library-independent representation of semantic entities and semantic relationships.

It is intended to serve as a shared intermediate representation across multiple domains, including:

- software/code auditing,
- scientific and technical text examination,
- document and LaTeX analysis,
- evidence and provenance tracking,
- future ontology and knowledge-graph workflows.

The graph core is not defined by NetworkX, SciPy, RDF, OWL, a graph database, or any single analysis library. Those systems consume or project the Semantic Graph through adapters.

The core architectural direction is:

```text
Domain extractors / LLM outputs
            |
            v
    Universal SemanticGraph
            |
    -------------------------
    |          |            |
    v          v            v
 NetworkX    SciPy       RDF / OWL
```

The Semantic Graph is therefore the semantic source of truth. Backends are derived computational or interchange representations.

---

## 2. Current Core Model

The current implementation defines three core dataclasses:

```python
SemanticNode
SemanticEdge
SemanticGraph
```

The canonical in-memory fields are:

### SemanticNode

```python
node_id: str
entity_type: str
attributes: Dict[str, Any]
metadata: Dict[str, Any]
```

### SemanticEdge

```python
source_id: str
target_id: str
relation_type: str
attributes: Dict[str, Any]
metadata: Dict[str, Any]
```

### SemanticGraph

```python
nodes: List[SemanticNode]
edges: List[SemanticEdge]
```

The list-based node and edge containers are part of the current implementation, but are not a requirement imposed by any backend.

---

## 3. Core Semantic Invariants

### 3.1 Node identity

`node_id` identifies a semantic entity within a graph.

A node identifier should be:

- stable enough to support reproducible references,
- unique within a graph,
- independent of backend-specific integer indexing,
- independent of visualization coordinates,
- independent of storage-engine identifiers.

Examples:

```text
module.main
function.audit.parse
claim.001
paper.doi.10_1234_example
section.methods
equation.wave_equation
```

Backend adapters may create their own local integer or database identifiers, but must retain a reversible mapping to `node_id`.

### 3.2 Entity type

`entity_type` classifies what a node represents.

The core does not impose a closed global enumeration.

Examples may include:

```text
SoftwareModule
Function
Class
ScientificClaim
ResearchPaper
EvidenceItem
Concept
Equation
DocumentSection
Requirement
```

Domain vocabularies may constrain or extend allowed values in their own layer.

A backend must not reinterpret `entity_type` as a backend-native implementation type.

### 3.3 Edge semantics

An edge represents a directed typed semantic relationship.

The canonical edge identity is determined by:

```text
source_id
target_id
relation_type
```

plus optional attributes and metadata.

Examples:

```text
IMPORTS
CALLS
DEPENDS_ON
SUPPORTED_BY
CONTRADICTS
DERIVED_FROM
REFERENCES
DEFINES
EXPLAINS
```

The core does not impose a closed global relation vocabulary.

Parallel edges between the same node pair are permitted because two entities may participate in multiple semantic relationships.

---

## 4. Attributes and Metadata

The graph deliberately separates `attributes` from `metadata`.

### 4.1 Attributes

`attributes` describe the represented entity or relationship.

Examples:

```json
{
  "language": "python",
  "complexity": 12
}
```

or:

```json
{
  "confidence": 0.91,
  "statement": "The reported configuration increased transmission loss."
}
```

Attributes belong to the semantic description of the represented thing.

### 4.2 Metadata

`metadata` describes the record, extraction, provenance, or processing context.

Examples:

```json
{
  "source": "paper.pdf",
  "extractor": "llm",
  "created_at": "2026-09-15T00:00:00Z"
}
```

or:

```json
{
  "repository_path": "audit_engine/semantic_audit/core/semantic_graph.py",
  "extraction_pass": "ast-import-analysis"
}
```

Metadata should not silently replace domain semantics that belong in `attributes`.

---

## 5. Provenance

The current core provides `metadata` on both nodes and edges. This is the minimum compatibility hook for provenance.

G2.5 does not require a dedicated provenance class yet.

However, future provenance work must be able to represent at least:

- source document or source file,
- extraction method,
- extraction agent,
- creation or observation time,
- confidence or uncertainty where applicable,
- transformation history,
- source location or span where applicable.

Future PROV-O alignment may map provenance metadata into a more formal model, but the graph core must remain usable without RDF or PROV-O libraries.

---

## 6. Serialization Contract

The current JSON-compatible serialization maps in-memory field names to portable serialized names.

### Node serialization

```text
node_id      -> id
entity_type  -> type
attributes   -> attributes
metadata     -> metadata
```

### Edge serialization

```text
source_id      -> source
target_id      -> target
relation_type  -> relation
attributes     -> attributes
metadata       -> metadata
```

Canonical serialized shape:

```json
{
  "nodes": [
    {
      "id": "module.main",
      "type": "SoftwareModule",
      "attributes": {},
      "metadata": {}
    }
  ],
  "edges": [
    {
      "source": "module.main",
      "target": "module.research",
      "relation": "IMPORTS",
      "attributes": {},
      "metadata": {}
    }
  ]
}
```

The difference between in-memory names and serialized names is intentional and must be documented rather than treated as a schema inconsistency.

---

## 7. Domain Independence

The graph core must not encode domain-specific assumptions.

The same core model must be able to represent:

### Software graph

```text
module.main
    |
    | IMPORTS
    v
module.research
```

### Scientific reasoning graph

```text
claim.001
    |
    | SUPPORTED_BY
    v
paper.123
```

### Document graph

```text
section.methods
    |
    | DEFINES
    v
concept.boundary_condition
```

Domain-specific validation belongs in separate vocabulary or policy layers.

---

## 8. Backend Independence

Backend adapters are projections of the Semantic Graph.

A backend must not redefine the core graph schema.

### 8.1 NetworkX

NetworkX is a computational graph backend.

Typical uses:

- graph traversal,
- reachability,
- path analysis,
- centrality,
- connectivity,
- visualization support.

The adapter may project the Semantic Graph into a `MultiDiGraph`, but the Semantic Graph remains authoritative.

### 8.2 SciPy

SciPy-oriented graph algorithms typically require matrix or sparse-matrix representations.

A SciPy adapter may construct:

- node-to-index mapping,
- adjacency matrix,
- weighted adjacency matrix,
- sparse graph representation.

The adapter must preserve a reversible mapping:

```text
semantic node_id <-> numerical matrix index
```

Loss of semantic identifiers during numerical projection is not acceptable unless the loss is explicitly declared and the mapping is retained separately.

### 8.3 RDF / OWL

An RDF adapter may map:

```text
node_id       -> RDF resource
relation_type -> RDF predicate
target node   -> RDF object
```

RDF or OWL semantics are optional layers. The core does not depend on an RDF library or ontology reasoner.

### 8.4 Other backends

The same rules apply to:

- igraph,
- graph-tool,
- SNAP,
- graph databases,
- visualization systems,
- embedding or machine-learning systems.

---

## 9. Adapter Preservation Contract

Every backend adapter must explicitly define what it preserves.

At minimum, a lossless semantic adapter should preserve:

- node identity,
- entity type,
- edge direction,
- relation type,
- node attributes,
- edge attributes,
- node metadata,
- edge metadata.

If a backend cannot preserve one or more of these directly, it must:

1. retain the information in a side mapping, or
2. declare the projection as lossy.

Silent information loss is prohibited.

---

## 10. Adapter Mutation Rule

A backend representation is derived state.

Changes made directly to a backend graph must not automatically be treated as authoritative changes to the Semantic Graph.

Canonical modification should occur through Semantic Graph APIs or through an explicit synchronization operation.

This avoids accidental semantic divergence between:

```text
SemanticGraph
```

and:

```text
NetworkX / SciPy / RDF / database projection
```

---

## 11. Graph Construction and LLM Use

The graph may be constructed from deterministic tools, LLM extraction, or combinations of both.

Examples:

```text
Python AST -> SemanticGraph
LLM text extraction -> SemanticGraph
LaTeX parser -> SemanticGraph
Evidence pipeline -> SemanticGraph
```

LLM-generated graph content must not receive special structural privileges.

The same contracts apply regardless of producer.

Where uncertainty exists, it should be represented explicitly in attributes or metadata rather than being hidden.

---

## 12. Code Audit and Text Audit as Peer Domains

Software auditing and text/scientific auditing are peer consumers of the graph core.

Neither domain should define the universal schema.

A software vocabulary may define entities such as:

```text
SoftwareModule
Function
Class
Import
Configuration
Contract
```

A scientific-text vocabulary may define:

```text
ScientificClaim
EvidenceItem
ResearchPaper
Concept
Method
Equation
Observation
```

Relations can likewise be domain-specific.

Cross-domain relations are allowed where useful.

For example:

```text
ScientificClaim
    |
    | IMPLEMENTED_BY
    v
SoftwareFunction
```

This capability is one reason the universal graph should remain open and extensible.

---

## 13. Current Implementation Assessment

The current `semantic_graph.py` already satisfies several G2.5 requirements:

- it has no dependency on NetworkX or SciPy,
- it supports arbitrary node and edge attributes,
- it supports arbitrary node and edge metadata,
- it supports directed typed relationships,
- it can represent parallel semantic relationships,
- it serializes semantic identifiers and metadata,
- it contains no hard-coded software-only or scientific-only type restrictions.

The following are not yet enforced by the implementation and should remain explicit future decisions rather than accidental behavior:

- duplicate `node_id` policy,
- dangling-edge policy,
- graph-level metadata,
- graph/schema versioning,
- formal provenance schema,
- domain vocabulary validation,
- adapter loss reporting,
- deterministic ordering requirements,
- serialization/deserialization round-trip contract.

These are G2.5/G3 follow-up concerns, not reasons to reshape the core around a backend.

---

## 14. Validation Requirements

G2.5 validation should eventually verify:

### Domain-independence test

Construct both a software graph and a scientific/text graph using the same core classes.

### Serialization preservation test

Verify that node and edge identity, type, relation, attributes, and metadata survive serialization.

### NetworkX preservation test

Verify that the current NetworkX adapter preserves required semantics.

### Future SciPy projection test

Verify a reversible node-id/index mapping.

### Backend isolation test

Verify that the core does not import backend libraries.

### Loss declaration test

Any deliberately lossy adapter must identify which information is omitted.

---

## 15. Stability Rule

After G2.5 is accepted, changes to the following fields should be treated as architecture-level changes:

```text
SemanticNode.node_id
SemanticNode.entity_type
SemanticNode.attributes
SemanticNode.metadata

SemanticEdge.source_id
SemanticEdge.target_id
SemanticEdge.relation_type
SemanticEdge.attributes
SemanticEdge.metadata
```

Changes to serialized names should also require an explicit compatibility decision.

Domain vocabularies and backend-specific fields may evolve independently without changing this core contract.

---

## 16. Decision Summary

The Semantic Graph is a universal semantic interchange and reasoning structure.

Its role is:

```text
meaning-preserving intermediate representation
```

rather than:

```text
wrapper around a specific graph library
```

NetworkX, SciPy, RDF/OWL, graph databases, and future libraries must adapt to the graph.

The graph must not adapt its meaning to them.

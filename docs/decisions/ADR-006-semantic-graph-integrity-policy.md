# ADR-006: Semantic Graph Integrity and Identity Policy

**Status:** Accepted for G2.5 validation  
**Date:** 2026-09-15  
**Decision scope:** Universal Semantic Graph integrity  
**Depends on:** ADR-005 — Preserve a Universal Semantic Graph Core

---

## Context

G2.5 established that one library-independent `SemanticGraph` should support multiple domains and multiple backend representations.

The same graph core is expected to represent, among other things:

- software modules, symbols, imports, calls, and dependencies,
- scientific claims, evidence, papers, methods, and concepts,
- document and LaTeX structures,
- future cross-domain relationships.

The graph will also be projected into multiple computational and semantic systems such as NetworkX, SciPy sparse structures, RDF/OWL, igraph, graph-tool, SNAP, and possible graph databases.

That makes graph integrity rules part of the semantic contract rather than a backend detail.

The current implementation already models:

```text
SemanticNode
    node_id
    entity_type
    attributes
    metadata

SemanticEdge
    source_id
    target_id
    relation_type
    attributes
    metadata
```

The unresolved questions are:

1. whether duplicate `node_id` values are allowed,
2. whether edges may reference missing nodes,
3. whether repeated/parallel relationships are allowed,
4. whether self-loops are allowed,
5. whether graph-level metadata and schema-version fields should be introduced immediately.

---

## Decision 1 — `node_id` is unique within one graph snapshot

A canonical `SemanticGraph` must contain at most one node for a given `node_id`.

Therefore:

```text
add node A(id = X)
add node B(id = X)
```

must fail rather than silently:

- overwrite A,
- merge A and B,
- ignore B,
- create two competing nodes with the same identity.

### Rationale

`node_id` is the graph-local semantic identity key.

Silent duplicate handling would make the meaning of edges ambiguous and would produce backend-dependent behavior.

For example:

- NetworkX normally treats one node key as one node,
- sparse matrix adapters require one node-to-index mapping,
- RDF projections typically require one resource identity,
- graph databases normally need an explicit identity or uniqueness strategy.

The core should therefore make identity ambiguity visible.

---

## Decision 2 — Identity resolution is not the same as duplicate insertion

Two observations that might represent the same real-world thing must not be merged merely because an extractor or LLM believes they are equivalent.

If equivalence is uncertain, the domain layer should preserve distinct identities and represent the resolution explicitly.

Conceptually:

```text
ObservedEntity_A
ObservedEntity_B
        |
        v
IdentityResolution decision
```

This keeps identity resolution auditable.

The core graph therefore rejects duplicate identifiers while still allowing higher-level identity-resolution models.

---

## Decision 3 — Canonical graphs reject dangling edges

A `SemanticEdge` may only be added when both:

```text
source_id
target_id
```

already exist as nodes in the graph.

This means:

```text
A --RELATION--> B
```

requires both A and B to be represented explicitly.

### Rationale

This provides a stable contract for:

- NetworkX,
- SciPy node-index mappings,
- graph databases,
- semantic validation,
- future RDF/OWL export.

A parser or streaming extractor that discovers a relationship before an endpoint must first create an appropriate node or use a separate staging structure.

An incomplete extraction state is not the same thing as a valid canonical semantic graph.

---

## Decision 4 — Stub nodes are preferable to dangling references

Some sources reveal a relationship before the system knows much about the referenced entity.

The preferred representation is an explicit minimally described node rather than a missing endpoint.

Example:

```text
node:
    id = source.unknown_17
    type = UnresolvedEntity

edge:
    claim.4 REFERENCES source.unknown_17
```

Whether a domain uses `UnresolvedEntity`, another domain type, or a richer placeholder policy belongs to the domain vocabulary layer.

The universal graph only requires the endpoint to exist.

---

## Decision 5 — Parallel edges are allowed

The graph remains a directed attributed multigraph.

Therefore multiple edges between the same pair of nodes are valid.

Examples:

```text
A IMPORTS B
A CALLS B
```

or:

```text
Claim_1 SUPPORTED_BY Paper_1
Claim_1 SUPPORTED_BY Paper_1
```

where the two support edges may record different evidence locations, extractors, timestamps, or provenance.

The graph core must not deduplicate such edges automatically.

Deduplication is a domain-level semantic decision.

---

## Decision 6 — Self-loops are allowed

The core does not prohibit:

```text
A RELATION A
```

because valid domains may require them.

Examples include:

- recursive software calls,
- reflexive semantic relations,
- provenance or transformation models that legitimately point to the same semantic identity.

A domain vocabulary may forbid particular self-relations if required.

---

## Decision 7 — Graph-level metadata is not added to the core yet

G2.5 keeps the current minimal `SemanticGraph` fields:

```text
nodes
edges
```

Graph-level execution context, run metadata, repository identifiers, timestamps, and similar information should not be added until their ownership and lifecycle are defined.

This avoids turning the graph core into a catch-all container.

Node- and edge-level metadata remain supported.

---

## Decision 8 — The current serialized payload remains version-compatible

The current serialized shape remains:

```json
{
  "nodes": [],
  "edges": []
}
```

No top-level `schema_version` field is added in this step.

The current JSON Schema and architecture documentation define the G2.5 contract externally.

Before the graph becomes a long-lived external interchange format, a versioned envelope should be designed deliberately.

That future design may look conceptually like:

```json
{
  "schema": {
    "name": "semantic_graph",
    "version": "..."
  },
  "graph": {
    "metadata": {}
  },
  "nodes": [],
  "edges": []
}
```

but that envelope is not adopted by this ADR.

This avoids breaking existing G1/G2 artifacts while still recording versioning as a required future boundary.

---

## Decision 9 — Backend projections must preserve these invariants

Every backend adapter must preserve or explicitly map:

```text
unique semantic node identity
directed edge endpoints
relation type
attributes
metadata
parallel-edge semantics
```

For matrix-oriented backends such as SciPy, a reversible mapping must exist:

```text
node_id <-> matrix index
```

For backends that cannot directly retain some semantic information, loss must be declared rather than hidden.

---

## Compatibility with the current software graph builder

The existing `SemanticGraphBuilder` already follows the intended construction order:

```text
check has_node
    |
    v
add node if missing
    |
    v
add edge
```

and creates source/target nodes before import and symbol relationships.

Therefore the stricter core policy is compatible with the currently observed builder design.

---

## Domain-specific caution

The uniqueness rule does **not** mean different semantic levels should be collapsed.

For text and scientific workflows, these may need distinct identities:

```text
ClaimOccurrence
Proposition
PropositionVersion
EvidenceSnapshot
SourceIdentity
SourceRepresentation
CitationOccurrence
```

Multiple textual occurrences of one proposition are not automatically duplicate nodes.

They are different semantic entities connected by explicit relationships.

The universal core enforces identity integrity; domain layers decide what counts as the same entity.

---

## Consequences

### Positive

- ambiguous duplicate identities fail early,
- backend mappings become deterministic,
- SciPy index construction becomes well-defined,
- RDF resource mapping is clearer,
- malformed LLM-generated graphs fail closed,
- graph traversal does not encounter undeclared endpoints,
- identity resolution remains explicit and auditable.

### Costs

- extractors must create endpoint nodes before edges,
- import/staging pipelines may require placeholder nodes,
- accidental duplicate generation will now raise an error,
- upstream builders that relied on silent duplication would need correction.

These costs are accepted because a canonical semantic graph should represent a coherent state rather than an incomplete ingestion buffer.

---

## Deferred

The following remain separate future decisions:

- graph-level metadata ownership,
- versioned serialization envelope,
- formal provenance schema,
- domain vocabulary validation,
- deterministic serialization ordering,
- deserialization and round-trip behavior,
- adapter capability/loss-reporting API,
- identity across graph snapshots and repository revisions.

---

## Final rule

The canonical graph follows:

```text
one node_id -> one semantic node per graph snapshot

every edge endpoint -> an explicit node

parallel semantic relationships -> allowed

self-relations -> allowed unless a domain forbids them
```

These rules are core integrity constraints, not backend-specific behavior.

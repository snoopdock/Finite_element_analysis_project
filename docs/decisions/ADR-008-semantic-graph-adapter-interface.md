# ADR-008: Common Semantic Graph Adapter Interface

**Status:** Accepted for G2.5 Step 5

## Context

The Semantic Graph is designed as a universal semantic representation.

Multiple backend systems will consume this graph:

- NetworkX
- SciPy
- RDF / OWL
- graph databases
- visualization systems
- future numerical or reasoning libraries

Without a shared adapter contract, each backend may implement incompatible assumptions.

## Decision

All backend adapters should implement a common conceptual interface.

The interface does not replace backend implementations.

It defines the responsibilities every adapter must expose.

## Required Adapter Responsibilities

### 1. Export

Convert:

SemanticGraph

into:

backend-specific representation

Example:

SemanticGraph -> NetworkX MultiDiGraph

---

### 2. Capabilities

Every adapter must describe:

- directed graph support
- multiedge support
- self-loop support
- metadata support
- attribute support
- reversibility

---

### 3. Identity Mapping

Adapters must expose the relationship between:

semantic identifiers

and

backend identifiers

Example:

```
claim.paper.001 <-> 42
```

---

### 4. Loss Reporting

Adapters must explicitly report unsupported semantics.

Example:

A sparse matrix adapter may preserve:

- connectivity

but not:

- metadata
- relation names

Loss must be visible.

---

## Non-Goals

This ADR does not:

- implement SciPy adapter
- implement RDF export
- define ontology rules
- define provenance ontology

It only defines the adapter boundary.

---

## Architectural Rule

The dependency direction remains:

SemanticGraph

        |

        v

Adapter Interface

        |

        v

Backend Implementation

The backend never becomes the source of semantic truth.

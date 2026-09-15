# ADR-010: SciPy Sparse Projection Contract

**Status:** Proposed for G2.5 Step 7  
**Scope:** Design of numerical sparse graph projections

---

## Context

The SemanticGraph is a semantic representation layer.

SciPy sparse structures are numerical computation structures.

They are not equivalent representations.

The purpose of a SciPy adapter is therefore not to replace SemanticGraph, but to create a computational projection.

Architecture:

SemanticGraph

        |

        v

SciPy Adapter

        |

        v

Sparse Matrix Representation

---

## Decision 1 — SemanticGraph remains authoritative

The sparse matrix is a derived computational artifact.

The following remain outside the matrix:

- node metadata
- edge metadata
- relation semantics
- provenance
- extraction information

---

## Decision 2 — Node identity requires explicit mapping

SciPy matrices require integer indices.

Therefore:

semantic identity

must map to:

integer matrix index

Example:

```text
claim.001 -> 0
paper.001 -> 1
```

The mapping must be stored and reversible.

---

## Decision 3 — Relation types cannot collapse silently

Semantic relations:

```text
IMPORTS
CALLS
SUPPORTED_BY
REFERENCES
```

have different meanings.

A single adjacency matrix cannot represent all relation semantics safely.

Future implementations should consider:

- one matrix per relation type
- relation encoded sparse tensors
- explicit edge tables

The choice is deferred until implementation.

---

## Decision 4 — Metadata requires side channels

Sparse matrices can represent numerical values.

They do not naturally represent:

```json
{
 "confidence":0.95,
 "source":"paper.pdf"
}
```

Metadata must remain available through auxiliary structures.

---

## Decision 5 — Loss reporting is mandatory

A SciPy adapter must report:

Preserved:

- connectivity
- direction (if representation supports it)
- numerical weights

Potentially transformed/lost:

- relation labels
- metadata
- provenance

---

## Non-goals

This ADR does not implement:

- scipy adapter
- matrix format
- relation tensor design
- numerical algorithms

It only freezes architectural boundaries.

# ADR-011: SciPy Adapter Hybrid Sparse Projection (Option C)

**Status:** Accepted for G2.5 Step 8

## Context

SciPy provides numerical sparse graph operations but is not a semantic graph representation.

The Universal Semantic Graph remains authoritative.

## Decision

The SciPy adapter uses a hybrid projection:

1. Sparse topology matrix
2. Semantic node index mapping
3. Relation side-channel
4. Metadata side-channel

Representation:

```
SemanticGraph

      |

      v

SciPyAdapter

      |

      +-- adjacency_matrix
      |
      +-- node_index_mapping
      |
      +-- relation_mapping
      |
      +-- metadata_sidecar
```

## Preserved

- graph connectivity
- direction
- numeric edge values
- deterministic node indexing

## External side channels

The following remain outside the matrix:

- semantic node IDs
- relation names
- node metadata
- edge metadata
- provenance

## Loss reporting

The adapter must explicitly report:

- preserved semantics
- transformed semantics
- unavailable semantics

## Non-goals

This step does not implement:

- numerical graph algorithms
- FEM coupling
- automatic semantic inference

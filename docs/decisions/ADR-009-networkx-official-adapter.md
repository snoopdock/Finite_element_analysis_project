# ADR-009: NetworkX as the First Official Semantic Graph Adapter

**Status:** Accepted for G2.5 Step 6

## Context

The SemanticGraph core was intentionally separated from graph computation libraries.

G2.5 established:

- universal semantic graph representation,
- graph integrity rules,
- backend projection contract,
- adapter interface.

The existing NetworkX backend was previously a wrapper around the graph model.

It now becomes the first adapter implementing the formal adapter contract.

## Decision

NetworkXAdapter implements:

```python
SemanticGraphAdapter
```

and provides:

- export()
- capabilities()
- identity_mapping()
- loss_report()

## Preservation

The NetworkX adapter preserves:

- node identity
- entity type
- node attributes
- node metadata
- edge direction
- relation type
- edge attributes
- edge metadata
- parallel edges
- self-loops

## Loss Policy

Current NetworkX projection is considered lossless because:

- MultiDiGraph supports directed multigraph semantics.
- Nodes may contain arbitrary attributes.
- Edges may contain arbitrary attributes.

## Architecture

```
SemanticGraph

      |

      v

NetworkXAdapter

      |

      v

NetworkX MultiDiGraph
```

The direction is one-way by default.

SemanticGraph remains authoritative.

## Future Work

Future adapters:

- SciPy sparse adapter
- RDF adapter
- graph database adapter

must implement the same contract.

# ADR-012: Semantic Graph Backend Capability Registry

## Status
Accepted for G2.5 Step 9

## Purpose
Provide a discovery layer for Semantic Graph backend adapters.

The registry describes backend capabilities without replacing adapter implementations.

## Architecture

SemanticGraphAdapter

        |

        v

Capability Registry

        |

        +-- NetworkX
        |
        +-- SciPy
        |
        +-- Future RDF / graph database adapters

## Responsibilities

The registry stores:

- backend identifier
- adapter reference
- supported capabilities
- loss characteristics

## Non-goals

The registry does not:

- execute graph operations
- replace adapters
- perform semantic reasoning

Adapters remain responsible for implementation.

# ADR-013: Semantic Graph Backend Selection Policy

## Status

Accepted for G2.5 Step 10

## Context

The Semantic Graph supports multiple backend adapters.

Current adapters:

- NetworkX
- SciPy

Each backend has different capabilities.

A mechanism is required to select an appropriate backend based on task requirements.

## Decision

Introduce a backend selection policy layer.

The selection layer consumes capability information from the Backend Capability Registry.

Architecture:

```
Task Requirements

        |

        v

Backend Selection Policy

        |

        v

Capability Registry

        |

        v

Backend Adapter
```

## Responsibilities

The selector evaluates:

- required capabilities
- semantic preservation requirements
- computational requirements

## Examples

Semantic traversal:

Requirements:

```
metadata=True
multiedges=True
```

Suitable:

```
NetworkX
```

Numerical sparse operations:

Requirements:

```
sparse_matrix=True
```

Suitable:

```
SciPy
```

## Non-goals

The selector does not:

- perform graph operations
- modify adapters
- replace capability registry
- perform semantic reasoning

Adapters remain responsible for execution.

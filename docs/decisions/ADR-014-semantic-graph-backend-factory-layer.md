# ADR-014: Semantic Graph Backend Factory Layer

## Status

Accepted for G2.5 Step 11

## Context

The Semantic Graph backend architecture now contains:

- Backend Capability Registry
- Backend Selection Policy
- Multiple backend adapters

The selection policy identifies a suitable backend, but another layer is required to create the actual adapter instance.

## Decision

Introduce a Backend Factory layer.

Architecture:

```
Task Requirements

        |

        v

Backend Selection Policy

        |

        v

Backend Factory

        |

        +----------------+
        |                |
        v                v

 NetworkXAdapter    SciPyAdapter
```

## Responsibilities

The factory:

- receives a backend identifier
- receives a SemanticGraph instance
- creates the appropriate adapter
- hides adapter construction details

## Non-goals

The factory does not:

- select backends
- analyze capabilities
- execute graph algorithms
- replace adapters

Selection remains the responsibility of BackendSelectionPolicy.


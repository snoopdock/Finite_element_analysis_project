# ADR-017: Backend Execution Result Contract

## Status

Accepted for G2.5 Step 13

## Context

The backend architecture now supports:

- capability discovery
- backend selection
- backend creation
- execution context

Different backends naturally return different output formats.

Examples:

NetworkX:
- graph objects

SciPy:
- sparse matrices

Future RDF:
- semantic triples

A common result boundary is required.

## Decision

Introduce BackendExecutionResult.

Architecture:

```
BackendExecutionContext

        |

        v

Backend Adapter

        |

        v

BackendExecutionResult

        |

        +-- output
        +-- backend metadata
        +-- provenance
        +-- transformations
        +-- loss report
```

## Responsibilities

BackendExecutionResult provides:

- backend identification
- returned artifact
- execution metadata
- semantic transformation information
- loss reporting

## Non-goals

The result contract does not:

- modify backend outputs
- replace backend-specific APIs
- perform semantic reasoning

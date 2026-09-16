# ADR-019: Backend Pipeline Result Integration

## Status

Accepted for G2.5 Step 15

## Context

The BackendPipeline previously exposed adapter details to callers by returning:

- adapter instance
- backend name

The backend architecture already contains:

- capability registry
- selection policy
- backend factory
- execution context
- execution result contract

A stable pipeline boundary is required.

## Decision

BackendPipeline returns BackendExecutionResult directly.

Architecture:

Request

    |

    v

BackendPipeline

    |

    +--> Selection Policy

    +--> Backend Factory

    +--> Execution Context

    +--> Adapter

    +--> Result Contract

    |

    v

BackendExecutionResult

## Benefits

- removes backend details from callers
- provides stable API boundary
- simplifies future backend additions
- improves interoperability

## Non-goals

The pipeline does not:

- implement backend algorithms
- replace adapters
- perform semantic reasoning

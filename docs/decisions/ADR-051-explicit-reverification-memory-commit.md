# ADR-051: Explicit Re-verification Memory Commit

## Status
Accepted for G3.2.2.

## Context
G3.2.0 established audit memory as append-only historical storage. Automatically persisting every execution result would couple execution to storage policy and make dry-run/replay behavior harder to reason about.

## Decision
`IncrementalReverificationExecutor` has no long-term-memory dependency and performs no persistence. A separate `ReverificationExecutionMemoryRecorder` performs an explicit, idempotent commit of successor artifacts and the execution result.

## Consequences
Execution can be tested or inspected without side effects. Storage policy remains caller-controlled, while persisted records remain content-addressed and append-only.

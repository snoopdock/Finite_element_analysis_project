# ADR-060: Explicit Orchestration Integration Memory Commit

## Status
Accepted

## Decision
G3.3.2 orchestration/integration results are persisted to `AuditLongTermMemory` only through an explicit recorder. Planning, adaptive execution, reconciliation, and bridge preparation have no automatic memory side effects.

All committed artifacts are bound to the after-snapshot and remain historical evidence rather than current semantic authority.

## Consequences
Partially executed or caller-rejected orchestration work cannot silently become durable audit knowledge. Repeated identical commits remain idempotent through content-addressed memory records.

# ADR-048: Audit Memory Query Model

## Status

Accepted for G3.2.1.

## Context

G3.2.0 made audit memory append-only and non-authoritative. Incremental auditing requires historical lookup by snapshot, evidence, receipt, rule, and artifact identity without turning memory into a semantic database that can validate or promote knowledge.

## Decision

Provide a read-only query service over immutable `MemoryRecord` values.

Supported filter dimensions are:

- artifact type;
- artifact identity;
- snapshot identity;
- evidence identity;
- verification receipt identity;
- rule identity.

Non-empty filter categories combine with logical AND. Results are deterministically ordered by record identity, and query identity is content-addressed.

## Authority Boundary

Historical presence proves only that a record was stored. It does not prove that the represented claim remains current, valid, or true.

Queries may not mutate memory, canonical semantic graphs, candidate knowledge, findings, receipts, or verification state.

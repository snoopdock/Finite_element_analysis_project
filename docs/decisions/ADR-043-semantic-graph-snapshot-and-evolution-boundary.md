# ADR-043: Semantic Graph Snapshot and Evolution Boundary

## Status

Accepted.

## Decision

Graph evolution is represented by immutable snapshots and explicit deltas. The canonical `SemanticGraph` remains the semantic authority and is not mutated by snapshot or diff operations.

A snapshot binds graph content to its `SemanticContext`. A delta reports observed structural and semantic-context changes between two snapshots.

## Consequences

- Repository history can be reasoned about without redefining graph identity.
- Graph changes become reproducible audit artifacts.
- A topology change is an observation, not an audit finding.
- Parallel edge payload changes are conservatively represented as edge removal plus edge addition because the G2 core has no independent edge occurrence identifier.

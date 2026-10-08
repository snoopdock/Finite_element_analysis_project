# ADR-044: Impact-Aware Invalidation and Recheck Semantics

## Status

Accepted.

## Decision

G3.2 distinguishes three lifecycle assessments for artifacts across graph transitions:

- `current`
- `recheck_required`
- `stale`

A semantic-context change or removal of directly referenced evidence makes an artifact stale. A graph change with no direct evidence loss requires re-verification but is not treated as proof that the artifact is invalid.

## Rationale

Treating every graph change as invalidation would destroy useful audit memory. Treating every historical conclusion as current would permit semantic drift. The three-state model preserves both caution and evidence.

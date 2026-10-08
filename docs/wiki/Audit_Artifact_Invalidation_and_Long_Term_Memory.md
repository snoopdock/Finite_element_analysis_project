# Audit Artifact Invalidation and Long-Term Memory

## Why memory needs invalidation

A verified conclusion can become unsafe to reuse after the repository changes. Conversely, throwing away every result after every commit defeats the purpose of cumulative auditing.

G3.2 therefore separates direct invalidation from conservative rechecking.

## Direct invalidation

An artifact becomes stale when:

- the semantic interpretation context changes; or
- evidence explicitly referenced by the artifact disappears.

## Recheck requirement

If the graph changes elsewhere, the previous artifact is retained but marked as requiring re-verification.

This is particularly important for absence-based checks: adding a new relation may invalidate an earlier conclusion even when no previously referenced evidence was removed.

## Durable memory

The audit-memory ledger stores historical serialized artifacts bound to snapshots. It does not mutate the canonical graph and it does not promote candidate knowledge when loaded.

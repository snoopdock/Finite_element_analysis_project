# ADR-046: Incremental Impact Propagation Model

## Status

Accepted for G3.2.1.

## Context

G3.2.0 introduced immutable semantic-graph snapshots, graph deltas, coarse invalidation semantics, and an append-only audit-memory ledger. Its conservative invalidation rule intentionally classified any graph change without direct evidence loss as `recheck_required`. That rule is safe, but it cannot distinguish a distant, irrelevant graph edit from a change inside the semantic neighborhood actually used by an analysis.

The repository now needs incremental re-verification without weakening the existing evidence/verification/rule boundaries.

## Decision

Introduce explicit **change atoms**, **artifact dependency profiles**, and a dependency index. Impact propagation is performed over audit artifacts rather than over backend graph objects.

A dependency profile may record:

- graph and semantic-context fingerprints;
- source and referenced node identities;
- evidence identities;
- observation identities;
- relevant relationship types;
- upstream audit-artifact identities;
- the analysis impact scope.

The supported propagation chain is:

```text
Graph change
   ↓
Analysis
   ↓
Verification receipt
   ↓
Finding
```

Semantic-context changes and removal of directly referenced evidence are invalidating. Changes in a relevant local neighborhood require recheck. Proven-unrelated changes may remain current for bounded local analyses.

## Interpretation Boundary

Impact is not a finding. A structurally affected artifact is not thereby false, unsafe, or scientifically invalid. Impact only determines whether prior audit work can still be relied on without re-execution.

## Consequences

Positive:

- unrelated changes no longer force global audit rechecks when locality can be established;
- invalidation lineage is explicit and reproducible;
- downstream artifacts inherit upstream invalidation state;
- multigraph evidence identities remain the basis for direct evidence loss.

Costs:

- analyses must expose sufficient scope information to justify locality;
- unknown/global analysis types remain conservative;
- future analysis types must define their impact scope before benefiting from fine-grained invalidation.

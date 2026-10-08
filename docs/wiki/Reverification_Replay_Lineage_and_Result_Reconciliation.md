# Re-verification Replay, Lineage, and Result Reconciliation

## Why replay is necessary
An analysis artifact is evidence about a particular graph state under a particular semantic context. When that state changes, the old artifact is historical evidence, not a reusable current result.

Replay creates a successor artifact rather than mutating the predecessor.

## Lineage model

```text
Analysis A(t)
    │ replay
    ▼
Analysis A(t+1)

Receipt R(t)
    │ rebind + verify
    ▼
Receipt R(t+1)

Finding F(t)
    │ reevaluate rule
    ├──► Finding F(t+1)     if still triggered
    └──► no successor       if not reproduced
```

The absence of a successor does not delete the predecessor.

## Evidence identity
Exact evidence replay is intentionally stricter than semantic-observation replay. If provenance or edge metadata changes, the evidence fingerprint changes. An observation-scoped rule may explicitly reselect the same semantic relation and use its new evidence, while an exact-evidence obligation must not silently substitute a different record.

## Scientific interpretation
Reconciliation answers:

> What happened when the old audit obligation was evaluated against the new graph state?

It does not answer:

> Was the historical finding wrong?

That distinction protects audit history and keeps temporal reasoning explicit.

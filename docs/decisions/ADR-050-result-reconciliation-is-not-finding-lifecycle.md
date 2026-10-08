# ADR-050: Result Reconciliation Is Not Finding Lifecycle

## Status
Accepted for G3.2.2.

## Context
After re-verification, a previous finding may still be triggered, may no longer trigger, may become ineligible, or its target may disappear. Treating these outcomes as direct lifecycle mutations would rewrite historical audit state and blur the distinction between "what was true of the prior audit" and "what the current audit reproduces."

## Decision
Re-verification produces immutable `ArtifactReconciliation` records. Reconciliation describes predecessor-to-successor relationships but does not mutate historical `AuditFinding.lifecycle_status`.

Examples include:

- `finding_persists`;
- `finding_not_triggered`;
- `finding_ineligible`;
- `target_no_longer_present`.

A historical finding remains part of the append-only record even when a later re-verification does not reproduce it.

## Consequences
A future policy layer may decide whether a non-reproduced finding should be marked resolved, suppressed, or otherwise dispositioned. G3.2.2 deliberately does not make that policy decision.

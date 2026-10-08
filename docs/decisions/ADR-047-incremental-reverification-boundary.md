# ADR-047: Incremental Re-verification Planning Boundary

## Status

Accepted for G3.2.1.

## Context

After impact propagation identifies stale or recheck-required artifacts, the repository needs a deterministic description of what must be recomputed. Coupling impact analysis directly to analyzers, verifiers, or rule execution would turn graph evolution into an execution authority and would collapse boundaries established in G3.0 and G3.1.

## Decision

G3.2.1 introduces a **re-verification planner**, not an executor.

The planner may create three actions:

- `rerun_analysis`;
- `reverify_receipt`;
- `reevaluate_finding`.

Tasks preserve upstream prerequisites. Priority is calculated under a versioned policy from explicit operational factors such as validity state, impact reason, artifact stage, and existing finding severity.

Priority is triage metadata only. It is not semantic truth, confidence, scientific importance, or finding severity.

## Forbidden Couplings

The planning layer must not:

- execute graph analysis;
- invoke verification services;
- execute semantic rules;
- create audit findings;
- promote candidate knowledge;
- mutate a canonical semantic graph.

## Consequences

A later orchestration milestone may consume the plan, but execution semantics can evolve independently from impact analysis and priority policy.

# ADR-049: Re-verification Replay and Execution Boundary

## Status
Accepted for G3.2.2.

## Context
G3.2.1 can identify affected audit artifacts and produce an ordered re-verification plan. The next step is executing that plan without turning the executor into a second planner, semantic authority, or graph mutator.

## Decision
G3.2.2 introduces explicit replay and execution boundaries.

The executor may only execute tasks already present in a `ReverificationPlan`. Analysis replay reconstructs backend-neutral `GraphQuery` intent from prior analysis artifacts. Verification replay requires an explicit selection mode:

- `exact_ids`;
- `observation_semantics`;
- `analysis_scope`.

The replay catalog records this selection intent instead of inferring it from the shape of an old artifact.

## Invariants

- no task invention during execution;
- execution graph must match the plan's after snapshot;
- prerequisite artifacts execute before downstream artifacts;
- canonical graph mutation is forbidden;
- candidate promotion is outside this boundary;
- missing semantic targets are `not_applicable`, not fabricated failures.

## Consequences
The executor becomes deterministic and reproducible. Historical intent must be available explicitly; missing replay metadata is treated conservatively rather than guessed.

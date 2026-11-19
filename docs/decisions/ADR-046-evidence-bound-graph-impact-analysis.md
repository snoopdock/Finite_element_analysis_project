# ADR-046 — Evidence-bound graph impact and dependency analysis

- **Status:** Accepted for E.8.4 implementation; rebased on E.8.3.1
- **Date:** 2026-11-19

## Context

The repository already exposes generic graph neighbors, path and dependency analysis. The LLM-facing tool set did not provide explicit direct/transitive dependency grouping or reverse-impact analysis for a changed file, module or symbol.

## Decision

Extend the existing `graph_neighbors` registered tool with bounded modes: `dependencies`, `dependents` and `impact`. Do not add more function schemas to the LLM tool catalog.

Impact analysis first resolves immediate ownership relations, then follows incoming import, dependency, call, workflow-invocation and test relationships. Results include direct/transitive candidates, exact evidence IDs, paths and truncation status.

## Consequences

- Impact analysis works from file, module or symbol identifiers.
- All graph operations use the selected E.8.3 backend and reference parity.
- Partial traversals are explicitly marked incomplete.
- Static graph observations are not represented as runtime proof or severity.
- Results are read-only inputs for a future deterministic action planner; they do not authorize changes or execution.


## Corrective parent

E.8.4 is based on E.8.3.1, not the failed E.8.3 package. G6.1/G6.2 side-channel parity tests remain in G9.42 targeted validation alongside the E.8.4 impact suites.

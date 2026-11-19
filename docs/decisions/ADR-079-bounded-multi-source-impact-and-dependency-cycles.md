# ADR-049: Bounded multi-source impact and dependency-cycle analysis

- **Status:** Accepted for AE-32C E.8.6
- **Date:** 2026-11-19
- **Scope:** Stage1 only

## Context

E.8.4 added evidence-bound impact analysis for one changed entity. Real engineering changes commonly span multiple files, modules, or symbols. Repeated single-source calls force the caller to merge overlapping candidates and can hide shared impact. The project also needs a deterministic way to surface dependency cycles within the affected region without converting structural observations into an unsupported severity judgement.

## Decision

1. Extend `QueryType.IMPACT` to accept 1–25 unique source entities.
2. Keep the LLM-facing `graph_neighbors` tool stable and add an optional `changed_nodes` list (up to 24 additional selectors) for `direction="impact"`.
3. Normalize source order and allocate the global traversal budget across sources.
4. Merge candidates by semantic node ID and preserve per-source attribution, paths, and evidence IDs.
5. Detect strongly connected components in the bounded impacted subgraph using only `IMPORTS` and `DEPENDS_ON`.
6. Use an iterative SCC algorithm to avoid recursion limits.
7. Emit evidence-bound structural risk indicators, not a scalar risk/severity score.
8. Mark any traversal or cycle-scan limit explicitly as incomplete.
9. Preserve the read-only and no-execution authority boundary.

## Alternatives considered

### Require callers to issue one impact query per changed entity

Rejected because each caller would need to implement deterministic deduplication, overlap attribution, and shared budget enforcement. It also creates inconsistent aggregation across LLM callers.

### Use a weighted risk score

Rejected because the repository does not yet have calibrated outcome labels or a validated mapping from graph structure to severity. A score would imply unsupported predictive validity.

### Enumerate all simple cycles

Rejected because the number of simple cycles can grow exponentially. Strongly connected components provide bounded, deterministic evidence that a cyclic dependency region exists without claiming to enumerate every cycle.

### Treat missing test edges as missing coverage

Rejected because absence of a graph edge is not proof that a test does not exist or does not exercise a component. E.8.6 reports only observed test candidates.

## Consequences

- The existing single-source impact request remains supported.
- Multi-source results are deterministic and order-independent.
- Shared impact is explicit.
- Dependency cycles are explainable through exact edge evidence.
- Incomplete analysis cannot be mistaken for complete absence of impact or cycles.
- Native backend acceptance remains separately governed by E.8.5 conformance evidence.
- The feature does not grant repository mutation or execution authority.

# G3.0 Semantic Analysis Runtime

## Status

Implementation checkpoint — query, traversal, dependency, path, evidence, and working-memory foundation.

## Purpose

G3.0 moves the semantic graph from representation and backend projection into bounded primitive analysis while preserving the G2/G2.75 authority boundaries.

The runtime deliberately separates four things:

1. **semantic graph state** — what entities and typed relationships are represented;
2. **primitive analysis** — what structure can be observed computationally;
3. **evidence and provenance** — why an observation exists and which graph snapshot produced it;
4. **verification / audit judgment** — whether the observation supports a violation or other conclusion.

The fourth item is intentionally not implemented by this milestone.

```text
SemanticGraph
    |
    v
Semantic Query
    |
    v
Primitive Analysis
    |
    v
Observation + Evidence
    |
    v
Working Memory
    |
    v
Future Verification / Audit Rules
```

## Neurosymbolic auditing influence

The design is informed by the evidence-seeking workflow described in Wang et al., *Neurosymbolic Code Auditing* (2026 survey manuscript): an auditor observes code and non-code artifacts, uses retrieval and primitive-analysis tools, accumulates evidence in working memory, and subjects candidate conclusions to explicit validation rather than treating a model prediction as authoritative.

The survey's observation–verification–memory framing maps to the repository as follows:

| Survey concept | Repository implementation |
| --- | --- |
| Observation | `SemanticObservation` |
| Primitive program facts | typed semantic edges + bounded graph analysis |
| Working memory | `AuditWorkingMemory` |
| Evidence | `EvidenceRecord` |
| Verification | explicit `VerificationStatus`; current graph analysis emits `observed` only |
| Durable reusable artifact | versioned `semantic_graph_analysis/v1` JSON |
| Invalidation under change | graph-content fingerprint and stale-result detection |

## Scientific / epistemic boundary

Graph reachability is not equivalent to semantic truth.

Examples:

- an `IMPORTS` path demonstrates represented dependency structure, not architectural invalidity;
- a shortest graph path demonstrates topology, not runtime path feasibility;
- a centrality score (future work) would express structural centrality, not scientific importance;
- a graph edge extracted by a tool is `observed` evidence until a stronger verifier promotes it.

## Determinism

G3 analysis artifacts use content-derived identifiers and graph fingerprints. Equivalent semantic graph snapshots produce equivalent fingerprints independent of insertion order. This supports reproducible CI artifacts and allows working memory to detect stale results after semantic graph changes.

## Implemented analyses

### Structural

One-hop semantic neighborhood under optional relation and direction filters.

### Dependency

Direct or transitive typed reachability. Default dependency relations are intentionally conservative: `IMPORTS` and `DEPENDS_ON`. Other relationships such as `USES` and `CALLS` require explicit query scope.

### Path

Deterministic shortest observed path under direction, relation, and depth constraints. Path existence is deliberately labeled as observation, not executable feasibility.

## Deferred

- policy/architecture violation rules;
- solver-backed feasibility checking;
- executable witnesses;
- LLM-based semantic validation;
- long-term audit memory;
- cost-aware orchestration;
- automatic remediation;
- scientific-content verification.

These should build on the evidence and lifecycle contracts introduced here rather than bypass them.

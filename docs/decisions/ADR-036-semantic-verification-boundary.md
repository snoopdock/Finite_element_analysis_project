
# ADR-036: Semantic Verification Boundary

## Status
Accepted for G3.1.0.

## Context
G3.0 established backend-independent graph queries, primitive analysis, observations, evidence records, and task-local working memory. Those artifacts describe what is represented in the canonical semantic graph, but they do not establish policy violations, program feasibility, or scientific truth.

A direct `GraphAnalysisResult -> AuditFinding` path would conflate structural observation with judgment.

## Decision
The repository SHALL use the following dependency direction:

```text
Canonical SemanticGraph
        -> primitive graph analysis
        -> SemanticObservation / EvidenceRecord
        -> VerificationObligation
        -> Verifier
        -> immutable VerificationReceipt
        -> SemanticAuditRule
        -> AuditFinding
```

Graph-analysis modules SHALL NOT import the verification, rule, or finding layers. Verification modules SHALL NOT create findings. Rules SHALL consume verification receipts rather than re-running graph algorithms.

## Consequences
- structural reachability cannot silently become a violation;
- different verification mechanisms can coexist behind a common contract;
- verification and policy can evolve independently;
- scientific-content and software-architecture audits can share the same verification substrate while retaining domain-specific rules.

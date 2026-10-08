# Semantic Graph Foundations and G3 Evolution

## Purpose

This page records the architectural line from the closed G2 semantic-graph backend work into G3 semantic analysis and verification. It is intended to prevent later implementation work from collapsing representation, computation, verification, and policy into one layer.

## Closed foundation: G2

G2 established a canonical, library-independent `SemanticGraph` and replaceable computational backends. NetworkX and SciPy are projections used for computation; they do not own semantic identity. Mapping and representational loss must remain explicit.

G2 is closed. Its authority boundary is:

```text
semantic meaning -> canonical graph -> explicit backend projection
```

## G2.75 semantic-integrity decisions

The later architectural review clarified identity, projection, provenance, vocabulary governance, and the distinction between raw observations and interpreted semantic claims. The key rule is that the owner of meaning owns identity. Graph nodes represent semantic objects; they do not replace domain identity.

## G3.0: semantic analysis runtime

G3.0 introduced backend-independent queries and primitive structural analysis:

- structural neighborhood queries;
- dependency reachability;
- observed shortest semantic paths;
- deterministic graph and analysis identities;
- evidence records with preserved edge provenance;
- task-local working memory.

G3.0 deliberately stops at observations. A graph path is not runtime feasibility, and a dependency is not automatically an architectural violation.

## Research influence

Three research directions informed the transition beyond G3.0.

### Neurosymbolic auditing

The auditing survey frames robust auditing as an evidence-seeking workflow organized around **observation, verification, and memory**. This directly motivated the separation of graph observations from verification obligations and durable receipts.

### Graph neural networks and neural-symbolic computing

The GNN/neural-symbolic survey shows multiple hybrid arrangements between learned and symbolic reasoning and highlights the tension between effective learning and sound reasoning. G3 therefore isolates learned or heuristic proposals as candidate knowledge and reserves canonical authority for explicitly verified artifacts.

### Large-scale semantic-network modeling

The semantic-network review emphasizes that analytical outputs depend on how entities and relationships were represented. G3.1 therefore binds analysis and verification to a versioned semantic context in addition to a graph-content fingerprint.

## G3.1: verification and semantic audit layer

G3.1.0 establishes:

```text
GraphAnalysisResult
    -> VerificationObligation
    -> Verifier
    -> VerificationReceipt
    -> SemanticAuditRule
    -> RuleEvaluationResult
    -> AuditFinding
```

The layers have different responsibilities:

- **analysis** describes represented structure;
- **verification** tests an explicit bounded hypothesis;
- **rules** interpret verified outcomes under policy;
- **findings** are policy judgments linked to immutable receipts.

Evidence maturity is tracked separately from verification decision so that, for example, a deterministic verifier can produce validated evidence while refuting a hypothesis.

## G3.2: graph evolution and audit memory

The next graph milestone should introduce snapshot-aware semantics:

- graph snapshots;
- node/relation deltas;
- semantic-context deltas;
- reachability and boundary changes;
- structural-exposure changes;
- verification/finding invalidation;
- durable long-term audit memory.

Topological metrics remain observations. Baseline-relative changes may prioritize review, but centrality, clustering, or degree do not become semantic truth.

## G3.3: audit orchestration

Once observations, verification receipts, and long-term memory exist, orchestration can select verification depth according to risk, uncertainty, and cost. Stronger mechanisms may include static analyzers, solvers, tests, or executable witnesses.

## G4 and later: learned graph assistance

Embeddings or GNNs may later assist with candidate generation, semantic similarity, anomaly ranking, or audit prioritization. They should enter only after the repository has stable vocabularies, historical snapshots, validated labels, calibration criteria, and explicit provenance contracts.

## Permanent invariants

1. Backend IDs never replace semantic IDs.
2. Graph topology does not define semantic truth.
3. Analysis results are not findings.
4. Candidate knowledge is not canonical knowledge.
5. Verification does not define policy.
6. Rules do not silently upgrade evidence.
7. Findings require a triggered rule evaluation backed by a matching verification receipt.
8. Graph fingerprint and semantic-context fingerprint are both required for reproducibility and staleness checks.
9. Learned systems may propose; explicit verification governs canonical acceptance.

# ADR-045 — Unified native graph-adapter traversal contract

- **Status:** Accepted for E.8.3 implementation
- **Date:** 2026-11-19

## Context

AE-32B used NetworkX in the live query path while SciPy, igraph, graph-tool and SNAP adapters were registered or available elsewhere. Adapter presence did not establish live query-path use.

## Decision

All registered adapters implement a common native read-back contract. The selected backend is supplied by trusted configuration to `SemanticGraphAnalysisService`. The LLM cannot select or change it.

`SemanticGraph` remains canonical. Native node and edge projections are read back and compared against canonical identities, payloads and edge-occurrence IDs. AE-32 deterministic BFS constructs ordered results and evidence. Every accepted query is compared with the Python reference traversal.

SciPy is treated as a hybrid CSR-plus-side-channel projection. The CSR matrix is not represented as a lossless multigraph.

## Consequences

- One query and evidence contract across all registered adapters.
- Missing or incompatible explicit backends fail closed; no fallback.
- Native graph structures are used for adjacency/edge enumeration, while deterministic BFS remains authoritative.
- Native-library availability and versions are observable.
- Actual native smoke tests remain environment-specific for graph-tool and SNAP.
- RDFLib remains a separate RDF interchange/SPARQL subsystem, not a traversal backend.

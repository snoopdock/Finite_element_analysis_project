# ADR-044 — NetworkX Runtime Integration for Semantic Graph Queries

**Status:** Accepted for AE-32C E.8.2 implementation; pending fresh G9.42 GitHub validation.

## Context

The repository already contains a canonical `SemanticGraph`, a backend adapter interface, a capability registry, a backend selection policy, a factory, and a provenance-aware backend pipeline. NetworkX and SciPy are declared runtime dependencies. Optional adapters also exist for igraph, graph-tool and Stanford SNAP.

However, the AE-32B `RepositoryEvidenceTools` query path previously called `SemanticGraphAnalysisService` with the pure-Python `GraphTraversalEngine`. The external adapter/pipeline infrastructure was not part of the actual LLM-facing graph query execution path.

The existence of an adapter or an installed package is not evidence that a live query used it.

## Decision

1. **NetworkX is the first external computation backend activated in the AE-32B semantic query path.**
2. `SemanticGraph` remains the canonical source of semantic identity, relationships, attributes, metadata and evidence.
3. `BackendCapabilityRegistry`, `BackendSelectionPolicy`, `BackendFactory` and `BackendPipeline` construct the NetworkX adapter using explicit requirements for availability, directionality, multiedges, metadata and lossless projection.
4. NetworkX supplies a `MultiDiGraph` projection and its indexed adjacency access. AE-32 retains control of deterministic BFS ordering, query bounds, edge evidence creation, traversal result semantics and provenance.
5. Every accepted NetworkX traversal is compared, query by query, with the pure-Python `GraphTraversalEngine`. A mismatch, stale canonical graph, missing edge occurrence, or altered projection fails closed.
6. The backend is selected by trusted application configuration (`RepositoryEvidenceTools(graph_backend=...)`), never by an LLM-supplied tool argument. The default AE-32B query backend is `networkx`; `reference` remains available as an explicit oracle/baseline.
7. Runtime reports distinguish implementation presence, package availability, active backend, library version, projection identity, backend pipeline provenance, query counts and parity results.

## Canonical data and identity

The native NetworkX graph is a projection only. It is not the source of truth.

The adapter preserves:

- directed relationships;
- parallel edge occurrences;
- self-loops;
- semantic node IDs;
- entity types;
- node attributes and metadata;
- relationship types;
- edge attributes and metadata.

A private occurrence marker maps every NetworkX multiedge back to the exact canonical `SemanticEdge` occurrence. Backend-generated integer/key identities are never used as persistent semantic identities.

The projection is isolated from the canonical source. A source fingerprint is checked before and after traversal; source changes or projection corruption are rejected.

## Parity and result semantics

The application-owned deterministic BFS remains the traversal policy. NetworkX's `MultiDiGraph` provides the native indexed adjacency used to build the traversal adjacency lists. The pure-Python traversal is executed as a shadow oracle for each query.

Parity compares the complete traversal result, including:

- ordered traversal steps;
- visited nodes and paths;
- evidence records;
- examined-edge count;
- truncation state and stop reason;
- canonical graph fingerprint.

This is a correctness-first integration. The duplicate reference traversal adds computation overhead; E.8.2 makes no performance-superiority claim.

## Backend scope

| Backend | E.8.2 status | Reason |
|---|---|---|
| NetworkX | Active in AE-32B graph query path | Lossless directed multigraph projection with attributes and metadata |
| SciPy | Available; not active for semantic traversal | CSR matrix is numeric/connectivity-oriented; relation and metadata semantics remain side channels |
| igraph | Adapter present; not active | Requires separate real-library acceptance before activation |
| graph-tool | Adapter present; not active | Requires compatible native environment and real-library acceptance |
| SNAP | Adapter present; not active | Requires supported Stanford Snap.py environment and real-library acceptance |
| Python reference BFS | Available as oracle and explicit baseline | Retained for deterministic parity and fallback comparison |

No automatic backend selection or performance winner is authorized by this ADR.

## Security and authority

This change does not add repository execution, shell access, file writes, patch application, commits, pushes, or arbitrary model-defined actions. The LLM does not choose a graph backend. Repository code remains unexecuted during static audit and graph preflight.

The graph engine produces structural observations and evidence. It does not establish semantic truth, runtime behavior, scientific correctness, or diagnostic accuracy.

## Validation requirements

1. Verify adapter capability selection and provenance through the backend pipeline.
2. Verify parity with the reference traversal for outgoing, incoming and bidirectional queries; relation filters; depth and work limits; cycles; parallel edges; and self-loops.
3. Reject stale source snapshots and mutated/corrupt projections.
4. Verify AE-32B graph tools report NetworkX as the active backend and report real query/parity counters.
5. Verify AE-32C runtime architecture distinguishes active, available and merely implemented backends.
6. Run G9.42 on the exact Stage1 commit after upload and require full regression, detached evidence verification, immutable bundle publication and provenance catalog verification.

## Consequences

The external backend abstraction now participates in the actual LLM-facing graph query path. NetworkX usage is observable and machine-checkable. Other adapters remain available for later controlled integration without changing semantic query contracts.

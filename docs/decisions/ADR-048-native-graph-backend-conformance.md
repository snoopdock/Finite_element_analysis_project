# ADR-048 — Native Graph Backend Conformance and Acceptance States

**Status:** Accepted for AE-32C E.8.5 implementation; GitHub native CI acceptance pending.

## Context

E.8.3 integrated five registered graph traversal adapters. E.8.3.1 repaired SciPy side-channel parity and E.8.4 added graph impact/dependency analysis. The E.8.4 G9.42 run passed, but three optional native tests remained skipped because igraph, graph-tool and SNAP were not installed in the validation environment.

A passing mocked adapter test does not establish that the real binary/native library works. Package discoverability also does not prove that the native projection preserves semantic edge occurrences or metadata.

## Decision

1. Define one native conformance fixture and one backend-independent query matrix.
2. Verify native projection read-back against the canonical `SemanticGraph` before accepting query results.
3. Compare every native query result with the pure-Python reference traversal, including ordering, evidence, bounds, truncation and stop reason.
4. Repeat each query and require deterministic output.
5. Report adapter presence, package availability, native conformance and runtime compatibility as separate states.
6. Run native CI for NetworkX, SciPy, igraph and graph-tool in Python 3.11 environments.
7. Probe SNAP in the declared Python 3.11 runtime. If the published distribution is unavailable, keep it explicitly compatibility-blocked rather than lowering the project's Python requirement or treating a Python 3.9 test as project-runtime acceptance.
8. Keep RDFLib outside this traversal-backend decision; it remains the RDF interchange/SPARQL subsystem.
9. Keep backend choice outside LLM tool arguments. Explicit unavailable backend selection fails closed.

## Conformance semantics

The fixture includes directed relationships, duplicate parallel edges with identical relation labels, different relation labels on the same node pair, a cycle, a self-loop, an isolated node and nested JSON-compatible node/edge attributes and metadata.

Seven query cases cover outgoing, incoming, bidirectional, relation-filtered, depth-bounded, visited-node-bounded and step-bounded traversal. Each is executed twice and compared exactly with the reference engine.

## Consequences

- Native acceptance is evidence-backed and repeatable.
- Local optional-library skips are visible and cannot be misreported as passes.
- SciPy remains a hybrid CSR plus semantic side-channel backend; its native matrix is not claimed to store relation metadata itself.
- SNAP may remain an adapter-present but runtime-blocked backend until a supported Python 3.11 build is available and verified.
- No performance superiority claim is made; E.8.5 is a correctness/conformance increment.

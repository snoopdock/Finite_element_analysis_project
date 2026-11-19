# AE-32C E.8.3 — All registered graph backend adapters in the AE-32B query path

**Status:** implementation prepared; GitHub G9.42 validation required  
**Baseline:** E.8.2 validated Stage1 commit `eb4dac44a32d606b9949ce8af6b398fadde55708`  
**Scope:** `stage1/section-uuids` only

## Objective

Make every graph backend already registered in `BackendFactory` selectable by trusted AE-32B configuration and usable by the same `SemanticGraphAnalysisService` query path. Do not let the LLM choose or silently switch graph backends.

## Registered backends

| Backend | Query-path integration | Semantic preservation |
|---|---|---|
| NetworkX | Existing `MultiDiGraph` traversal adapter | Native multiedges and payload |
| SciPy | CSR adjacency plus exact edge-occurrence side channels | Matrix collapses parallel edges; side channels preserve exact relation, attributes and provenance |
| igraph | Native directed `Graph` vertex/edge iterators | Native vertex/edge properties checked against canonical graph |
| graph-tool | Native directed `Graph` vertex/edge iterators and property maps | Native vertex/edge properties checked against canonical graph |
| SNAP | Native `TNEANet` node/edge iterators and typed attributes | JSON-compatible attributes/metadata; compatibility depends on SNAP's supported interpreter |

The RDFLib subsystem remains the existing RDF interchange/SPARQL layer. It is not registered as a `BackendFactory` traversal adapter in this baseline and is not mislabeled as one.

## Runtime contract

- `SemanticGraph` remains the canonical source of truth.
- Backend selection is a trusted runtime setting: `networkx`, `scipy`, `igraph`, `graph-tool`, `snap`, or `reference`. The matched graph pilot accepts `--graph-backend` or `AE32C_GRAPH_BACKEND`; the selected backend is recorded in `run-context.json` and preflight evidence.
- The LLM receives no `select_graph_backend` tool and cannot switch backend at runtime.
- An explicitly selected backend that is missing, incompatible, or semantically mismatched fails closed. There is no silent fallback.
- AE-32 deterministic BFS continues to control ordering, traversal bounds, evidence construction and query semantics.
- Each accepted query is compared with the pure-Python reference traversal when parity verification is enabled.
- Node identities, edge occurrence identities, direction, parallel edges, relation labels, attributes and metadata are checked before evidence is returned.
- Runtime reports expose the selected adapter, native library version, projection type, backend pipeline provenance, transformations, loss assessment and parity counters.

The native libraries currently provide their graph representation and adjacency/edge enumeration. This increment does **not** delegate ordering-sensitive BFS to each library's independent traversal algorithm. That is deliberate: preserving one deterministic query contract is more important than claiming unmeasured algorithmic speedups.

## SciPy's hybrid representation

SciPy CSR stores directed connectivity and multiplicity counts. The exact per-edge relation, attributes, metadata and occurrence identity are joined from side channels. Runtime reports therefore keep `lossless=false` for the CSR matrix projection while separately reporting `exact_via_canonical_edge_side_channels` for the semantic query contract. Do not describe the matrix itself as a lossless multigraph.

## Optional native-library limitations

- NetworkX and SciPy are available through the repository's standard graph requirements.
- igraph can be installed with `pip install -e '.[graph-igraph]'`.
- graph-tool is an OS/conda-managed package; use the installation method for the target platform.
- The existing SNAP compatibility test documents a binary-only Python 3.9 smoke environment. The project declares Python `>=3.11`; therefore, SNAP activation in the standard runtime remains conditional on a compatible SNAP build/interpreter. The adapter is wired and contract-tested, but a passing fake-adapter test is not a real SNAP native smoke test.

Run the native smoke utility in each environment that actually has the relevant library:

```bash
python tools/gb02_backend_traversal_smoke.py --backend networkx
python tools/gb02_backend_traversal_smoke.py --backend scipy
python tools/gb02_backend_traversal_smoke.py --backend igraph
python tools/gb02_backend_traversal_smoke.py --backend graph-tool
python tools/gb02_backend_traversal_smoke.py --backend snap
```

A native smoke report must show the selected backend and `parity_verified_queries >= 1`.

## Safety and authority boundary

- Repository code is not executed.
- No network calls or provider calls are performed by the graph backend.
- The LLM can request only registered, bounded, read-only evidence operations.
- Backend choice remains trusted configuration.
- The deterministic action boundary remains `plan_only`; this increment does not grant repository modification or command execution authority.

## Validation

Contract tests exercise all five registered adapters. Real NetworkX and SciPy paths are tested in the available local runtime. Real igraph, graph-tool and SNAP smoke tests run conditionally when those native libraries are installed; unavailable native libraries are skipped rather than represented as passed.

A fresh GitHub G9.42 run against the uploaded Stage1 commit remains the acceptance gate.

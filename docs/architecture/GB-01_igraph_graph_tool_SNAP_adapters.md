# GB-01 — Optional Native Graph Backend Adapter Extensions

Status: **Implementation ready for GitHub validation; native backends not yet acceptance-tested on an installed real library in the local environment.**

This is an **extension of the completed G6 backend infrastructure**, not a new G8 roadmap milestone. The compatibility profile identifier is `G8.1`; the roadmap remains G3/GE/G4/G5/G6/G7 as previously closed. No changes to scientific inference/verification or publication authority are introduced.

## Canonical contract

The source of truth remains `audit_engine.semantic_audit.core.semantic_graph.SemanticGraph`: directed, attributed, typed, supports parallel edge occurrences and self-loops. The native outputs are projections, *not* replacements for this model. New adapters implement the repository's `SemanticGraphAdapter` interface, `export()`, `capabilities()`, `identity_mapping()`, and `loss_report()`; they additionally expose `backend_graph()`, `nodes()`, `edges()`, and `neighbors()`.

| Backend key | Python package/import | Native graph type | Attribute encoding | Limits |
|---|---|---|---|---|
| `igraph` | `igraph` / `igraph` | `igraph.Graph(directed=True)` | native Python node/edge attributes | Native integer vertex/edge IDs, mapping supplied; Python object attr persistence not guaranteed for every output format |
| `graph-tool` | `graph-tool` / `graph_tool` | `graph_tool.Graph(directed=True)` | `string`, `object`, `int64_t` property maps | `object` maps are **in-memory**, not guaranteed portable through a graph-tool save/load |
| `snap` | `snap-stanford` / `snap` | `snap.TNEANet` | node/edge scalar attr columns, canonical JSON strings for nested attrs | Only JSON-compatible dictionaries, unsupported Python objects rejected explicitly |

Each adapter projects all edges as **distinct occurrences**, including two edges with the same endpoints and type. The mapping retains semantic node identifiers and an occurrence-to-native edge identifier index. `neighbors` produces distinct *outgoing* semantic neighbors matching the NetworkX adapter's semantics. Empty graph, detached in-memory copy, metadata preservation, invalid graph invariants, and missing libraries have tests.

**Do not use backend vertex indices as persistent identities.** The native graph can be modified after `export()`; the adapter's identity mapping describes the original projection only. Source data is deep-copied when creating the native representation; there is no automatic synchronization back to `SemanticGraph`.

## Lazy import and optional installations

`BackendFactory.create()` imports only the requested implementation. `BackendCapabilityRegistry` includes `available` for the optional libraries, and `BackendSelectionPolicy` skips unavailable backends. Installing a new native package after constructing a registry requires constructing a fresh registry.

- **igraph:** `python -m pip install igraph` or install from conda-forge.
- **graph-tool:** install in a compatible **conda-forge** environment, or on Ubuntu 24.04 install `python3-graph-tool` using `apt`. That Ubuntu package uses `/usr/bin/python3` (Python 3.12), **not** the `actions/setup-python` 3.11 virtual interpreter. The GB-01 manual workflow uses system Python for this branch.
- **Stanford SNAP:** `python -m pip install snap-stanford==6.0.0` in **CPython 3.9** on supported architectures; PyPI wheels for release 6.0.0 stop at Python 3.9. The GB-01 native workflow explicitly uses Python 3.9 for SNAP, not the normal 3.11/3.12 interpreters. The generic `snap` PyPI distribution is **not necessarily Stanford Snap.py**; the adapter rejects imports lacking `TNEANet`.

**No optional native packages are added to the repository's default `requirements.txt`.** Default full regression should run without these compiled libraries. Native smoke tests run separately in the manual workflow, one package at a time, and fail visibly if a compatible package cannot be installed. Dependency-failure is an environment/support constraint, *not* evidence of working native runtime support.

## Workflow acceptance gates

1. Add branch-specific files from the release patch. Run **Manual Validation Dispatcher** from `main`, profile `G8.1`, branch `stage1/section-uuids`, regression mode `profile`. This executes fake-native contract tests and full existing regression without installing the optional libraries.
2. Run **GB-01 Manual Optional Native Graph Backend Smoke** from `main` three times, selecting `igraph`, `graph-tool`, then `snap` on each manual invocation. The workflow installs only the requested native dependency and runs `source/tools/gb01_native_smoke.py` against the actual native graph API.
3. A backend is **native accepted only when its corresponding real-library smoke workflow passes**. If SNAP 3.9 binaries are unavailable on the runner, report it as **implementation-ready / native-unverified**, not a successful smoke check. Use a compatible Python/platform runner to complete it.

The native smoke verifies actual native vertex/edge counts, duplicate edge retention, self-loop, semantic IDs, typed relation labels and metadata. Artifacts capture the report and test log. Neither workflow commits, publishes, or modifies graph state; both are `workflow_dispatch` only.

## Known non-goals and caveats

- Backends remain computation projections; they do not add scientific reasoning rules or OWL entailment.
- No cross-backend performance claims are made here. For benchmarking, rerun G6 reproducible campaigns with a capability-aware workload after native environments are validated.
- Snap JSON is a deliberate restriction and the native string columns must be parsed when reconstructing complex attributes.
- The adapters do not implement imported graph round-trip to canonical SemanticGraph; canonical state must be retained separately.
- graph-tool object's non-portable metadata properties should not be presented as a format-preserving binary export.

## Reference APIs

- igraph: https://python.igraph.org/en/latest/api/igraph.Graph.html
- graph-tool: https://graph-tool.skewed.de/static/docs/stable/autosummary/graph_tool.Graph.html
- Stanford Snap.py `TNEANet`: https://snap.stanford.edu/snappy/doc/reference/graphs.html

# AE-32C E.8.5 — Native Graph Backend Conformance

**Status:** Implementation prepared; dedicated native CI acceptance pending.  
**Target:** `stage1/section-uuids` only.  
**Validated parent:** E.8.4, G9.42 run `44548545793`, commit `c17382c74b6cb0d85afc9457cc46a73150aeb07b`.

## 1. Purpose

E.8.5 establishes a reproducible native conformance contract for every registered semantic graph traversal backend. It distinguishes:

1. Adapter code being present.
2. A backend package being discoverable/importable.
3. The real native projection preserving the canonical semantic graph.
4. Native-backed queries matching the deterministic Python reference traversal.
5. A backend being accepted for the project's declared Python runtime.

A fake module can test an adapter's expected API contract, but it cannot satisfy native conformance. The E.8.3 fake-module tests remain useful unit tests and are not relabelled as native acceptance.

## 2. Conformance fixture

`tools/gb03_native_backend_conformance.py` creates a bounded in-memory `SemanticGraph` containing:

- five nodes with nested attributes and metadata;
- eight directed edge occurrences;
- three parallel occurrences between the same source and target, including two edges with the same relation label;
- one self-loop;
- a directed cycle;
- incoming and outgoing relationships;
- Unicode, booleans, numbers, lists, nested objects and null values in JSON-compatible payloads;
- one isolated node.

The runner reads the selected backend's actual projection back and compares every node payload and every edge occurrence with the canonical graph. It then executes seven traversal cases, each twice:

1. outgoing traversal;
2. incoming traversal;
3. bidirectional traversal;
4. relation-filtered traversal;
5. depth-bounded traversal;
6. visited-node-bounded traversal;
7. step-bounded traversal.

Every result must exactly match the Python reference `TraversalResult`, including ordered steps, evidence, visited nodes, truncation and stop reason. Repeated results must be deterministic. Backend query and parity counters must agree with the executed cases.

## 3. Backend acceptance matrix

| Backend | Native representation | Installation/acceptance route | E.8.5 position |
|---|---|---|---|
| NetworkX | `MultiDiGraph` | pip / `graph-core` | Native smoke passed locally; required in CI |
| SciPy | CSR plus exact semantic side channels | pip / `graph-core` | Native smoke passed locally; required in CI |
| igraph | directed `igraph.Graph` | pip / `graph-igraph` | Native CI job required |
| graph-tool | directed `graph_tool.Graph` with property maps | conda-forge Python 3.11 environment | Native CI job required |
| SNAP | `snap.TNEANet` | Published binary availability is conditional | Compatibility hold; native pass required before claiming acceptance |

RDFLib is not one of the five `BackendFactory` traversal adapters. Its RDF interchange and SPARQL functions remain a separate subsystem and are outside this E.8.5 matrix.

## 4. SNAP compatibility boundary

The project declares Python `>=3.11`. Stanford's Snap.py page identifies version 6.0 as released on 28 December 2020. Its linked installation matrix lists binary configurations for Python 3.5 through 3.9, not Python 3.11. The upstream page still gives a general Python 3.x statement, but the concrete published matrix is older and does not establish a Python 3.11 binary.

Therefore:

- E.8.5 does not lower the repository's Python requirement.
- The CI workflow probes whether `snap-stanford` is installable in Python 3.11.
- If it is installable, the real SNAP conformance runner must pass.
- If it is not installable, the evidence records `not_installed`/compatibility blocked; this is not a pass.
- A future source-build investigation may be undertaken separately, but an unpinned or unverified local build is not treated as accepted native support.

Official references (checked for this increment):

- Snap.py overview and installation: https://snap.stanford.edu/snappy/
- Snap.py installation matrix: https://docs.google.com/spreadsheets/d/1m-5gHUmGzh8XfLUCAY3eYvdcBA98TUMMusVZkwmpdaI/edit
- graph-tool conda installation: https://graph-tool.skewed.de/installation.html
- python-igraph supported Python versions and installation: https://python.igraph.org/en/develop/install.html

## 5. Dedicated native CI

`.github/workflows/e85-native-graph-backend-conformance.yml` is manually dispatched. It provisions:

- NetworkX, SciPy and igraph in Python 3.11 pip environments;
- graph-tool from conda-forge in a Python 3.11 environment;
- a separate Python 3.11 SNAP installability probe, which runs native conformance only if the real module is installable.

Each native run uploads a JSON report containing the backend name, library version, projection type, exact projection round-trip digest, case outcomes, reference parity counters and side-effect declarations.

The summary explicitly prohibits claiming five-backend native acceptance unless all five reports show `status=passed`. A SNAP probe-only report is not native conformance.

## 6. Safety and execution boundaries

The conformance runner:

- uses only an in-memory graph fixture;
- does not read or execute repository source;
- does not call providers or use API credentials;
- does not make network calls;
- does not modify repository files;
- does not execute shell commands or actions against the repository.

Backend selection remains trusted CLI/configuration input. The LLM cannot select a backend or bypass parity verification.

## 7. Local verification

The E.8.4 reconstructed baseline passed G9.42 locally before E.8.5 changes: 626 passed, 3 skipped.

On the current local Python 3.13.5 environment:

- NetworkX native conformance: passed, 7 cases repeated twice, 14/14 parity checks;
- SciPy native conformance: passed, 7 cases repeated twice, 14/14 parity checks;
- exact projection round-trip: 5 nodes and 8 edge occurrences for both backends;
- igraph, graph-tool and SNAP native libraries are not installed locally, so their real native tests are skipped here;
- fake-module adapter tests are not counted as native conformance.

The updated G9.42 targeted suite and full regression results are recorded in the package's `TEST_RESULTS.md`. GitHub validation on the exact uploaded Stage1 commit remains required.

## 8. Acceptance criteria

E.8.5 is accepted only when:

1. G9.42 targeted tests pass on the exact Stage1 commit.
2. Full repository regression passes with no failures or errors.
3. NetworkX, SciPy, igraph and graph-tool native CI reports each show `status=passed`.
4. Each report demonstrates exact node/edge projection round-trip and all seven query cases with 14/14 parity checks.
5. SNAP either passes the same native suite in Python 3.11 or remains explicitly classified as compatibility-blocked; it must never be silently marked accepted.
6. Detached evidence verification, immutable bundle publication and provenance catalog verification pass.

If SNAP remains blocked, report the release as **four native backends verified; SNAP adapter present but native acceptance blocked**. Do not describe all five as native-verified.

## 9. Next increment

After E.8.5's supported-native matrix is accepted, proceed to E.8.6: multi-file and symbol-level impact propagation, dependency-cycle analysis, test/workflow candidate mapping, and evidence-bound risk indicators. Keep impact output advisory and read-only until E.9 defines deterministic action planning and execution authority.

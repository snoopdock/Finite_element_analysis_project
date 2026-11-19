# AE-32C E.8.2 — External Graph Backend Integration

**Status:** Implementation package prepared; fresh GitHub G9.42 validation required.

**Target:** `stage1/section-uuids` only.

## 1. Why E.8.2 follows E.8.1

E.8.1 passed GitHub validation on run `44509867750`, Stage1 commit:

`b43ff39e5b5485c20c6362293e768866bfe0cc3a`

The validation report recorded 53 validation-engine tests, 483 targeted tests, and a full regression of 3,481 tests with 8 skips and no failures/errors. Detached evidence verification, immutable bundle publication and provenance catalog verification passed.

E.8.1 made the runtime architecture visible, but deliberately did not activate an external graph library in the live query path.

E.8.2 takes the next step: connect the existing backend abstraction to the actual AE-32B graph query path.

## 2. What changes

### 2.1 NetworkX is the first active external query backend

`RepositoryEvidenceTools` now defaults to the trusted configuration `graph_backend="networkx"`. An explicit `"reference"` option remains available for the pure-Python baseline and oracle.

The backend selection is not exposed to the LLM. No tool schema accepts a backend name.

The query construction path is:

```text
AE-32A static repository scan
        |
        v
Canonical SemanticGraph
        |
        v
SemanticGraphAnalysisService
        |
        v
BackendCapabilityRegistry
        |
        v
BackendSelectionPolicy
        |
        v
BackendFactory / BackendPipeline
        |
        v
NetworkXAdapter
        |
        v
NetworkX MultiDiGraph adjacency
        |
        v
AE-32 deterministic bounded BFS
        |
        +------> Pure-Python reference BFS (shadow parity)
        |
        v
GraphAnalysisResult + evidence + provenance
        |
        v
AE-32B evidence tools exposed to AE-32C LLM
```

NetworkX is therefore used in the actual AE-32B graph query path, not merely imported by a benchmark or reported as installed.

### 2.2 Deterministic semantics remain application-owned

The implementation intentionally does not hand result ordering, evidence construction, truncation or semantic interpretation to a third-party library.

NetworkX supplies a directed `MultiDiGraph` projection and indexed adjacency. AE-32 retains the deterministic BFS policy and its bounds.

Each NetworkX result is shadow-compared with the pure-Python reference result before it is returned. The comparison covers ordered steps, paths, visited nodes, evidence, examined edges, truncation and stop reason.

A mismatch fails closed. The canonical graph fingerprint is checked before and after execution. Mutated source snapshots, missing edge occurrences, altered node/edge payloads and projection identity mismatches are rejected.

This duplicates some computation. The initial objective is correctness and observability, not a claim of speed improvement.

### 2.3 Backend capability and provenance

The backend registry now checks actual runtime discoverability for NetworkX and SciPy rather than hardcoding both as available.

The query engine records:

- active backend and NetworkX version;
- native projection type and fingerprint;
- selected backend pipeline summary;
- backend provenance and transformation records;
- queries attempted, succeeded and failed;
- per-query parity checks and parity failures;
- examined edges and visited nodes.

AE-32C's runtime architecture report now reflects the actual backend used rather than hardcoding the Python reference traversal.

## 3. What is and is not active

| Backend | Status |
|---|---|
| NetworkX | Active for AE-32B semantic graph queries |
| Python reference traversal | Per-query correctness oracle; explicit baseline remains available |
| SciPy | Installed/available and used by existing sparse projection/benchmark code; not active for evidence-bearing semantic traversal |
| igraph | Adapter implementation present; not activated |
| graph-tool | Adapter implementation present; not activated |
| SNAP | Adapter implementation present; not activated |
| RDFLib | Representation/interchange and RDF query support; not the active traversal backend |

SciPy's sparse matrix does not itself preserve relation labels and edge metadata; those remain side channels. It is therefore not selected for evidence-bearing traversal in this increment.

The optional native adapters still require real-library smoke acceptance before they can be called active.

## 4. Runtime and action boundaries

The LLM can request only the registered AE-32B evidence tools. It cannot select the graph backend, issue arbitrary Python or shell commands, execute repository code, modify repository files, apply patches, commit or push.

The deterministic follow-up plan remains `plan_only`. No action execution or repository mutation is introduced.

Human reviewer packets and adjudication are not operational dependencies in this increment. Machine checks verify structural parity, evidence integrity and provenance; they do not claim semantic diagnostic correctness.

## 5. Local verification

Local environment: Python 3.13.5, NetworkX 3.6.1, SciPy 1.17.0.

| Check | Result |
|---|---:|
| G9.42 target modules | 37 |
| G9.42 targeted tests | **529 passed** |
| Focused integration tests | Passed |
| Python syntax / 3.11 grammar compatibility | Passed |
| JSON/YAML validation | Passed |
| Offline runtime architecture CLI | Passed |
| Offline graph-pilot preflight | Passed |
| Provider calls | 0 |
| Repository code execution | No |
| Full repository regression | Not completed locally; host execution was interrupted at 60 seconds |
| GitHub G9.42 validation | Pending |
| Live matched pair | Not run |

The preflight used the bounded `ae32c_core` scope:

- 102 indexed files;
- 1,315 semantic graph nodes;
- 5,954 graph edges;
- 36 edges examined by the target query;
- 21 discovered entities;
- complete, non-truncated query;
- NetworkX backend reported in the query result;
- per-query reference parity verified;
- no provider calls, repository code execution or source modifications.

A separate offline runtime architecture report on the reconstructed full source tree reported 10,510 graph nodes and 37,182 graph edges, with NetworkX 3.6.1 active in the query path. Its query counters were zero because that report command does not execute a graph query.

The 529 targeted tests are not a substitute for the full regression. GitHub validation must complete the full profile regression and evidence publication before E.8.2 is accepted.

## 6. Installation

Upload all files in `AE32C_E8_2_Stage1_Repository_Files.zip` to:

`stage1/section-uuids`

Do not upload anything to `main`.

Before uploading:

1. Compare every `replace` entry in `BASELINE_SHA256.json` against the current Stage1 file.
2. Confirm every `add` path is absent.
3. Stop if any replacement hash differs. Supply a fresh repository archive rather than applying the patch to an unknown baseline.
4. Upload all repository files together, including the tests, G9.42 profile and documentation.

Suggested commit:

```text
AE-32C E.8.2: integrate NetworkX into semantic graph query path
```

## 7. Post-upload acceptance

1. Run Manual Validation Dispatcher on the exact new Stage1 commit with profile `G9.42` and regression mode `profile`.
2. Require all targeted tests and the full regression to pass.
3. Require detached evidence verification, immutable bundle publication and provenance catalog verification.
4. Run the offline runtime architecture CLI and confirm:
   - `active_computation_backend = networkx`;
   - `backend_library = networkx`;
   - a NetworkX version is reported;
   - `backend_pipeline_wired_into_ae32b_query_path = true`;
   - SciPy, igraph, graph-tool and SNAP are not falsely marked active.
5. Run the offline graph-pilot preflight and confirm the graph query result reports:
   - `computation_backend = networkx`;
   - `backend_parity_status = verified_against_reference_per_query`;
   - complete, non-truncated query coverage.
6. Do not run a live matched pair as part of this validation step. A separate live pair requires its existing explicit manual authorization and bounded cost controls.

## 8. Next development increment

After E.8.2 is accepted, the next sensible work is to integrate a second real backend only after its semantics can be compared against the canonical graph and the NetworkX/reference results.

The likely order is:

1. Evaluate igraph as a second evidence-bearing directed multigraph backend, subject to real-library smoke acceptance.
2. Keep SciPy for sparse numeric operations unless a relation-aware, provenance-preserving query contract is introduced.
3. Add backend-specific performance measurements only after parity and native smoke gates pass.
4. Keep backend selection deterministic and application-controlled; do not allow the LLM to select or switch the computation engine.

The acceptance objective is not the number of installed libraries. It is a demonstrably active, replaceable computation backend whose results remain deterministic, provenance-bearing and semantically anchored to the canonical `SemanticGraph`.

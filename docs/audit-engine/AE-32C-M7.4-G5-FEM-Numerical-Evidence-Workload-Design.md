# AE-32C M7.4 G5 — FEM numerical-evidence graph workload design

**Status:** Workload design and repository evidence inventory; implementation and backend execution pending.  
**Branch:** `stage1/section-uuids`  
**Baseline:** `6fad135910d14dc47f086ec9d343eb1a7d04a265`

## 1. Purpose

The current M7.4 full-repository workload is source-derived but mostly exercises Python module dependencies, workflow/test relationships and change-impact traversal. It is not a domain-specific scientific workload. This design adds a FEM numerical-evidence graph task without inventing mesh data, field solutions, physical measurements or solver results that are not present in the repository.

The workload is intended to test whether each native backend can traverse the same typed scientific-evidence relationships and return the same result as the canonical reference engine. It is not a performance competition and does not establish numerical correctness by graph traversal.

## 2. Repository evidence inventory

The following artifacts were inspected on Stage1:

| Artifact | Observed content | Consequence for workload |
|---|---|---|
| `audit_engine/semantic_audit/ae11/numerics.py` | Deterministic high-precision Decimal checks for a bounded linear-static FEM data record; creates `FEMModel`, `EvidenceArtifact`, and seven `FEMNumericalCheck` nodes, with `EVIDENCED_BY` and `CHECKED_BY` edges | Real implementation and typed audit-observation graph are available |
| `tests/fixtures/ae11/spec.json` | Seven declared tolerances and a SHA-256-bound data artifact path | Can bind a query to the exact declared acceptance parameters |
| `tests/fixtures/ae11/bar_problem.json` | Three degrees of freedom, 3×3 stiffness matrix, loads, displacements, one fixed DOF, strain energy, units and four refinement levels | Small, actual repository FEM input fixture; suitable for traceability, not mesh-scale workload |
| `tests/semantic_audit/test_ae11_fem.py` | Independent bar-equilibrium oracle, seven invariant checks, known-defect mutations, malformed-data abstention, digest tampering and publication tests | Provides test and adversarial evidence nodes/relationships |
| `audit_engine/semantic_audit/ae11/METHOD_AND_LIMITATIONS.md` | Explicit assumptions, seven checks, provenance model and scientific limitations | Must be represented as scope/limitation evidence, not treated as a proof |
| `audits/fixtures/h6_fem_literature_manifest.yaml` | Four metadata-only literature sources with distinct scientific roles; no passage evidence or proposition links | Metadata can be represented as bibliography only; it must not become claim support |
| `formal/lean/FEA/FEM/WeakForm.lean`, `Stiffness.lean`, `Galerkin.lean`, `Convergence.lean` | Each file is currently empty (zero-byte blob) | They cannot be treated as formal proofs or as executable FEM specifications |

The AE-11 method document explicitly limits its verdict to seven necessary checks under declared assumptions. It does not verify governing equations, constitutive laws, mesh quality, physical loading, experimental data or the unknown true solution. The workload must preserve those limits.

## 3. Scientific scope

The accepted workload label is:

`FEM_LINEAR_STATIC_NUMERICAL_EVIDENCE_TRACEABILITY`

It is not labelled a general FEM solver, mesh/field simulation, magnetics workload, formal proof workload or scientific validation campaign.

The fixture contains a three-DOF bar/spring-style linear system with the declared analytic displacement vector `[0, 1, 2]`, stiffness matrix, load vector, fixed displacement and strain energy. The test file contains an independent arithmetic oracle for the declared fixture. The refinement series contains four values and is checked for monotonic error reduction and observed order.

All numerical facts must be loaded from the exact repository fixture and verified by its declared SHA-256. No test may synthesize additional physical measurements or claim the fixture is representative of industrial FEM scale.

## 4. Graph construction

Construct one immutable task graph by composing:

1. The repository source graph from `RepositoryEvidenceTools`, which provides file, module, symbol, test and workflow relationships.
2. The AE-11 report graph produced by `build_report(tests/fixtures/ae11/spec.json, tests/fixtures/ae11)`, which contains the source-bound FEM model, evidence artifact and seven check observations.
3. A narrow, versioned bridge layer that links AE-11 domain nodes to repository file/module/test nodes using exact paths, declared source hashes and observed test relationships.

The bridge layer must not infer scientific meaning from filenames alone. Every cross-layer edge must carry a provenance record naming the source path, source SHA-256, relation rule ID/version and the observed source fragment or structured field that justifies the edge.

Candidate typed relationships:

- `IMPLEMENTED_BY`: FEM numerical audit model to the exact AE-11 implementation module.
- `INPUT_ARTIFACT`: FEM model to the SHA-bound JSON fixture.
- `CONFIGURED_BY`: FEM audit to the specification and its seven tolerances.
- `CHECKED_BY`: FEM model to the seven observed numerical check nodes (already emitted by AE-11).
- `TESTED_BY`: implementation/check contract to the exact test module and test cases.
- `DOCUMENTED_BY`: audit contract to the method-and-limitations document.
- `PUBLISHED_BY`: assessment/report contract to the exact publication implementation.
- `WORKFLOW_VALIDATED_BY`: only if a workflow statically invokes the exact test or validation entry point; this edge records static wiring, not successful execution.

Use the repository's existing relation vocabulary where an exact equivalent exists. New relation types require a versioned vocabulary change and explicit schema compatibility tests; do not silently overload `IMPORTS` or `DEPENDS_ON` with scientific-evidence semantics.

## 5. Task suite

Each task is run against the same immutable composed graph, source hashes, rule/bridge versions and query seeds for every backend.

### T1 — Numerical-check provenance

Given `check:free_equilibrium_residual`, retrieve:
- the parent `FEMModel`;
- the exact `EvidenceArtifact` and SHA-256;
- the specification and relevant tolerance;
- implementation module and test evidence;
- the declared scientific limitations.

Acceptance requires exact typed paths and complete-for-query coverage. A check status is an observation from the deterministic audit, not independent proof of the model's physical correctness.

### T2 — Claim/evidence boundary

Given the literature manifest, retrieve its four source records and their `scientific_role` values. Verify that no source metadata creates a proposition, passage or support relation. The graph must distinguish bibliography metadata from actual evidence passages.

Acceptance requires zero inferred `SUPPORTS` or `EVIDENCES` claim edges from metadata-only records.

### T3 — Defect-to-test traceability

For each of the seven checks, trace the corresponding known-defect mutation test and the expected failure status. Separately trace malformed/unsupported input cases to the expected inconclusive/unassessed behavior.

Acceptance requires all seven invariant IDs to be covered by test evidence, with negative tests remaining distinct from positive oracle checks.

### T4 — Change-impact traversal

Starting from `audit_engine/semantic_audit/ae11/numerics.py`, retrieve connected tests, fixture inputs, method documentation and publication/verification code. Starting from `tests/fixtures/ae11/bar_problem.json`, retrieve the spec, numerical audit consumer and tests that bind its hash.

Acceptance requires source-derived relationships, bounded traversal, no repository mutation and parity with the reference engine.

### T5 — Formal-proof abstention

Query the four Lean FEM paths and inspect their source sizes/content status. Since they are empty, the engine must not report formalized weak-form, stiffness, Galerkin or convergence proofs.

Acceptance requires an explicit `empty_source` / `no_formal_evidence` result or equivalent abstention, not a formal-proof node inferred from the path name.

## 6. Backend acceptance

For NetworkX, SciPy, python-igraph, graph-tool and SNAP:

- build the same graph from the same immutable source snapshot;
- use identical task definitions, source hashes, query seeds and bounds;
- execute every task through the selected native backend;
- verify exact semantic parity with the reference graph engine;
- record backend-native adjacency operations and edge-occurrence reads;
- preserve parallel edges, self-loops, node/edge attributes and provenance;
- verify no repository writes, network/provider calls or target-code execution;
- record SNAP worker image, protocol, resource metrics and teardown.

A backend that cannot load or execute the graph within its declared envelope is reported as not executed/insufficient evidence, not as a pass and not as an inferior library. No backend is ranked or automatically selected.

## 7. Required adversarial cases

- alter the fixture after its declared hash is recorded;
- alter a tolerance without updating the spec hash/manifest;
- duplicate or omit one check node;
- alter one `CHECKED_BY` edge provenance record;
- add an unsupported scientific field to the fixture;
- insert a bibliography metadata record as a false proposition-support edge;
- claim a Lean proof for an empty Lean file;
- mutate a source file between inventory and content loading;
- remove a required test relation while leaving the test file present;
- corrupt one backend's native edge occurrence outside the query neighborhood;
- ensure incomplete graph coverage causes abstention, not a successful empty answer.

## 8. Acceptance boundary

This workload can provide domain-specific graph-native evidence for FEM numerical-audit traceability. It does not establish:
- correctness of the finite-element formulation or physical model;
- solver accuracy beyond the seven declared checks;
- mesh/field scale, mesh quality or industrial FEM performance;
- asymptotic convergence or error bounds;
- independent experimental validation;
- formal Lean verification;
- suitability of a backend for all 20 M7.4 task categories.

The current repository evidence is enough to construct this bounded workload, but the composed graph builder, bridge relation contract, task runner, adversarial tests and five-backend exact-source execution are not yet implemented. G5 remains **Partial** until those steps are completed. All 20 task/backend outcomes remain **Insufficient evidence**; `production_approval=false`.

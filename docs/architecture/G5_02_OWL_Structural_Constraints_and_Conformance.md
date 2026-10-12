# G5.2 — Source-bound OWL structural constraints and conformance

## Purpose

Build a deterministic, *fixed*, source-bound RDFS domain/range profile on top of the accepted G5.1 OWL vocabulary and G4 RDF export. Publish a detached N-Triples/Turtle axiom graph, a combined graph and a manifest bound to the exact verified GE graph snapshot and both G4/G5.1 manifest digests.

The profile is deliberately limited to **15 observed structural properties** of the project's own serialization. There are no user-supplied ontology imports, `owl:sameAs`, `owl:disjointWith`, property chains, or arbitrary class axioms. Scientific relationship predicates do not gain domain/range axioms from their labels. G5.1 existing schema is preserved byte-for-byte.

## Domain and range declarations versus validation

In standard RDF Schema/OWL semantics, `rdfs:domain` and `rdfs:range` typically support type *inferences*. They are not constraints that render a knowledge base inconsistent merely because an explicit type assertion is absent. Therefore:

1. G5.2 exports only carefully reviewed structural domain/range axioms (e.g., `containsNode` relates a graph snapshot to a semantic entity; `containsEdge` relates a snapshot to an RDF reified statement).
2. G5.2 separately performs a **finite, closed-world structural conformance check** over the source-bound exported RDF. It checks existing type assertions plus explicit G5.1 subclass declarations, literal datatypes and canonical forms, membership counts, unique node and edge occurrence fields, and all authority flags being false.
3. Successful checks **do not** establish an OWL model-theoretic consistency proof, scientific truth, validity of FEM equations, or permission to accept machine-generated claims. Those fields remain explicitly false in the manifest and report.

`attributesJson` and `metadataJson` are used on both nodes and reified edges; they receive `xsd:string` range declarations but no incorrect shared domain. `persistedGeneration` is optional in candidate export, required for persisted export.

## Dependency and provenance flow

```text
GE-02 verified graph / GE-01 candidate
        -> G4 RDF deterministic exporter and structural verifier
        -> G5.1 source-bound OWL vocabulary and verifier
        -> G5.2 reviewed structural axioms + separate finite conformance checker
        -> read-only evidence bundle, SHA-256 manifest and report
```

The output is written outside the source checkout. The verifier independently regenerates the expected G4, G5.1 and G5.2 datasets from the repository source. Rehashing an altered artifact cannot make it pass verification. Both `persisted` and `candidate` modes are available. No files are committed or pushed by the workflow.

## Scope and limitations

This step is **not** an OWL reasoner. It does not do arbitrary OWL-DL consistency or entailment reasoning, reasoning over scientific relation types, linked-data dereferencing, SPARQL endpoint hosting, automatic graph mutation, source evaluation or scientific approval.

Existing G3/GE/G4 review boundaries remain in force. Broader ontology modeling requires a separate, explicitly reviewed axiom selection stage; G5 should be closed only after its remaining acceptance criteria are addressed and validated.

## Validation

Use `validation/profiles/G5.2.yaml` with the unchanged **Manual Validation Dispatcher** (`stage1/section-uuids`, `G5.2`, `profile`), then run the new **G5.2 Manual OWL Structural Conformance Review** workflow from `main` in `persisted` mode (and optionally in `candidate` mode). Check `g5-structural-conformance.json` and `g5-structural-constraints-manifest.json` in the uploaded detached artifact. Full regression is a GitHub acceptance gate.

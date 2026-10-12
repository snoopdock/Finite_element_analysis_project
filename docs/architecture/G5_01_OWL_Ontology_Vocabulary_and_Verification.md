# G5.1 — Source-bound OWL Ontology Vocabulary and Verification

**Roadmap:** original **G5 — OWL Ontology**, after G4 RDF Export acceptance. G5.1 is the first implementation patch, **not the G5 completion declaration**.

## Contract

The existing GE graph store and G4 deterministic RDF exporter remain authoritative. G5.1 accepts either a GE-02 independently verified persisted state or a validated candidate scientific graph. It first requires G4's **full source-bound structural round-trip verification**; only then is an additional OWL/RDFS vocabulary projected into detached files.

The projection declares:

- `urn:fea:ontology:v1` as an `owl:Ontology` with the exact graph fingerprint, source snapshot and input digests, and G4 export manifest digest as immutable annotation assertions.
- The actual GE node entity types (such as `ScientificConcept`, `ScientificProposition`, `ScientificSourceRef`) as `owl:Class` resources under the shared `SemanticEntity` RDFS superclass.
- GE's direct semantic relation predicates and `containsNode`/`containsEdge` as `owl:ObjectProperty`.
- The G4 string/JSON/integer/boolean metadata predicates as `owl:DatatypeProperty`.
- A deterministic ontology-only RDF graph and an ontology+G4 graph union, in both N-Triples and Turtle, with a content-hashed JSON manifest.

The ontology deliberately does **not** introduce `owl:imports`, `owl:sameAs`, equivalence, disjointness, property chains, domain/range constraints, transitivity, functional properties, source-provided axioms or nonlocal dereference. Such semantic assertions require explicit domain modeling, tests and human acceptance before they can influence scientific review.

## Output

```text
ontology-schema.nt
ontology-schema.ttl
ontology-knowledge-graph.nt
ontology-knowledge-graph.ttl
owl-export-manifest.json
```

All artifacts are detached from the repository and must be emitted into a new directory outside the source checkout. G5.1 does **not** commit ontology files or mutate GE graph state.

## Verification

`verify_owl_layer()` reproduces ontology and combined graph bytes from the verified GE/G4 view and compares every byte, RDFLib-parsed N-Triples/Turtle triple sets, complete original G4 graph union, manifests, declared vocabulary, and explicit false authority flags. Recalculating file hashes after injecting triples or forging approval does not pass this check.

OWL vocabulary declaration is not OWL reasoning. No claim of logical satisfiability, OWL DL conformance, semantic entailment, scientific truth, or scientific-document approval is made at this stage. These aspects require later G5 development and separate user-reviewed gates.

## Manual execution

On `main`, dispatch **G5 Manual OWL Vocabulary and Source-Bound Verification**. Choose `branch=stage1/section-uuids`, `source_mode=persisted` (or `candidate` with repository-relative knowledge graph path). The workflow installs the development branch's requirements, runs G4.5/G4.6/G5.1 tests, builds detached ontology outputs, verifies their source-bound equivalence and report digest, and uploads evidence even if an earlier step fails.

Also run **Manual Validation Dispatcher** on `main` with branch `stage1/section-uuids`, profile `G5.1`, regression mode `profile`. G5.1's validation profile enables the complete repository regression gate.

Local CLI from a parent of the source checkout:

```bash
PYTHONPATH=source python -m audit_engine.semantic_audit.graph.owl_ontology build \
  --repository source --mode persisted --output-dir reports/ontology
PYTHONPATH=source python -m audit_engine.semantic_audit.graph.owl_ontology verify \
  --repository source --mode persisted --output-dir reports/ontology \
  --report reports/g5-owl-verification.json
```

For `candidate`, supply `--mode candidate --knowledge-graph examples/graph_engine/ge02_demo_graph.json` to both steps.

## G5 next tasks

The next G5 milestone should add a carefully reviewed domain-specific axiom policy and independent ontology consistency tests (with formally bounded entailment scenarios), while explicitly prohibiting the treatment of inferred RDF relations as scientific evidence. G5 can close only after real ontology interoperability, verification against stated constraints, and GitHub full regression pass.

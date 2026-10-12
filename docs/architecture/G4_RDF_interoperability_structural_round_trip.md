# G4.6 — RDF Interoperability and Structural Round-Trip Acceptance

**Roadmap:** Original **G4 — RDF Export**, distinct from the completed GE implementation detour. This is the second G4 integration patch following the deterministic G4.5 export module.

## Goal and trust boundary

Verify that an external RDF consumer can parse the two exported formats and recover the *same attributed graph structure* (including repeated edges) as the independently verified GE source. This is **not** an RDF importer, ontology reasoner, graph mutator, truth oracle, reviewer, or SAT authority escalation mechanism. In particular, `semantic_entailment_verified`, `scientific_truth_established`, `automatic_approval_permitted`, and `authoritative_graph_mutation_permitted` remain **false**.

## Concrete pipeline

1. Independently verify the GE-02 content-addressed persisted history (`HEAD.json`, commit and snapshot) or validate a candidate graph against GE-01's scientific adapter.
2. Generate deterministic G4.5 Turtle and N-Triples files with the existing `rdf_export` module, outside the source checkout.
3. Read files with the existing safe reader and check their SHA-256 manifest.
4. Parse both formats using RDFLib, compare their complete triple sets, and reject malformed or unexpected terms.
5. Reconstruct RDF nodes, exact JSON attributes/metadata, RDF reified statement edges, multiplicity indices, and direct relation triples. Compare node/edge **multisets** to the verified GE source.
6. Compare the entire RDF triple set and canonical publication bytes to an independently reprojected expected source graph, rejecting injected or omitted triples even if a detached manifest has been recomputed.
7. Write a deterministic content-addressed JSON report, outside the repository, with read-only authority flags. No RDF is written to the persistent GE store.

A verified round-trip attests *structural representation equivalence for this defined RDF vocabulary*. No general RDF semantic equivalence, ontology inference, scientific entailment, or empirical validation is claimed. RDF triple sets collapse duplicate direct edges, so the **reified occurrence resources** are necessary and explicitly validated to preserve the multigraph.

## Execute manually

**Full CI:** existing Manual Validation Dispatcher on `main`, target branch `stage1/section-uuids`, profile `G4.6`, regression `profile`. This profile includes both G4.5 and G4.6 tests plus full regression.

**Interop check:** `G4 Manual RDF Structural Interoperability and Round-Trip Verification` on `main`. `branch=stage1/section-uuids`, `export_mode=persisted` initially. Candidate mode supports a repository-relative path to a scientific knowledge graph JSON.

Manual CLI example from outside the source checkout:

```bash
PYTHONPATH=source python -m audit_engine.semantic_audit.graph.rdf_export \
  --repository source --mode persisted --output-dir reports/graph-rdf
PYTHONPATH=source python -m audit_engine.semantic_audit.graph.rdf_interoperability \
  --repository source --export-dir reports/graph-rdf --mode persisted \
  --report reports/rdf-interoperability-report.json
```

## Engineering constraints and limitations

- RDFLib 7.x is a required project dependency for this verification module, installed through `requirements.txt`.
- The verifier only accepts the project's `g4-rdf-export/v1` vocabulary and strictly canonical bytes. Arbitrary third-party RDF datasets are **not** trusted or imported.
- Triple counts, graph fingerprints, source hashes, manifest hashes, and GE store identifiers make results auditable, but SHA-256 checks **do not authenticate the producer** in an adversarial system absent signed provenance.
- This gate is not OWL support. Original G5 will add ontology structures and explicit reasoning contracts after G4 closure.
- The workflow is **manual-only** (`workflow_dispatch`); no push trigger, no branch writes, and no automatic document changes.

## Exit gate

Declare G4 completed only after (1) G4.6 Manual Validation Dispatcher full regression passes, (2) G4 manual interoperability artifact passes source-bound structural verification, and (3) the evidence and decision are reviewed. Both persisted and candidate paths have local tests; use a manual candidate-mode run for additional deployment coverage if desired.

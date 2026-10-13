# RI-02 — Scientific RDFLib Index and Source-Bound SPARQL Interoperability

Status: awaiting current-branch GitHub acceptance. Implementation milestone **RI-02**; numeric dispatcher compatibility profile `G8.3`. This is a post-G7 RDF interoperability enhancement, **not** a redefinition of original G4–G7 milestones.

## Motivation and architecture

The original G4 RDF export deliberately stores **losslessly reconstructed** `attributesJson` and `metadataJson` while G4.6 independently verifies the RDF against the GE graph snapshot. RI-01 added three named graphs (asserted RDF, approved node scalars, and provenance) with three fixed, bounded SPARQL queries. RI-02 makes selected scientific identifiers and relationship metadata directly queryable **without replacing the canonical exporter or source model**.

```
Verified GE-02 graph / candidate scientific JSON
    -> RI-01: G4.5 export + independent G4.6 structural verification
       -> canonical G4 assertion graph (unchanged)
       -> RI-01 scalar field graph (unchanged)
       -> RI-01 provenance graph (unchanged)
    -> RI-02: independently join every G4 reified edge occurrence to its GE edge
       -> scientific scalar index (new)
       -> index-vocabulary declarations (new)
    -> fixed SPARQL SELECT query -> detached N-Quads and report
    -> independently reconstruct from source, reparse, and compare bytes
```

Nothing in RI-02 is a scientific truth, OWL entailment or authorization to edit sources. Original G4/G5 serialization, GE-02 persisted history, G7 inference proofs and five computational graph adapters remain unchanged.

## Five named RDF contexts

1. **asserted:** exact G4 independently verified triple set; retains reified `rdf:Statement` for each parallel edge occurrence, with `rdf:subject`, `rdf:object`, relation type, ordinal and JSON metadata.
2. **fields:** RI-01-approved scalar node fields, unchanged.
3. **provenance:** RI-01 source fingerprint and read-only authority flags, unchanged.
4. **scientific-index:** typed scalar vocabulary from selected node attributes/metadata and **individual G4 statement resources**, not collapsed endpoint triples.
5. **index-vocabulary:** RDF property labels and explicit supported datatypes; descriptive vocabulary only. Neither OWL functional-property claims nor domain/range inferences are added.

All contexts have stable, fingerprint-derived IRIs. No blank nodes, remote RDF context loading, writable RDF source, storage plugin or general SPARQL input are accepted.

## Occurrence-aware join and safety invariant

Indexing must match the **multiset** of GE semantic edges against the independently G4-verified RDF statement resources, keyed by source IRI, target IRI, relation type, and canonical attribute/metadata maps. Identical edges consume distinct statement resources. This allows per-occurrence metadata queries without silently collapsing parallel edges into RDF triple-set semantics.

If an edge statement is missing, duplicated, altered, wrongly typed or ambiguous, the index aborts. A source citation with `source_verified=False` is only an **unverified citation reference**, never treated as evidence that the cited source supports the claim.

## Explicit query field policy

Nodes: `conceptName`, `propositionStatement`, `reviewStatusUnverified`, `frameworkName`, `sourceDeclaredType`, `sourceIdentifierUnverified`, `originalUUID`.

Reified edges: `claimedRelationTypeUnverified`, `relationStatusUnverified`, `edgeWeight`, `originalRelationshipUUID`, and the provenance/verification flags present in the GE source. JSON lists, objects, unknown attribute keys, non-finite weights, invalid scalar types and oversized indexed strings are **not silently coerced**. Unknown fields are not indexed; invalid values of *approved* fields fail closed.

### Bounded SPARQL catalog

| Query ID | Argument | Meaning |
|---|---|---|
| `nodes_by_indexed_field` | `name`, `statement`, `framework`, `status`, `type`, `source_id_unverified` | Return matching named scalar field values, max 200 |
| `concepts_by_status` | `proposed`, `draft`, etc. | Find scientific concepts with explicit unverified workflow status |
| `propositions_for_concept` | exact `SemanticNode.node_id` | Follow `HAS_CONCEPT` **as asserted**, preserving statement identity |
| `citations_for_entity` | exact `SemanticNode.node_id` | List `CITES_SOURCE` occurrences; *not* source verification |
| `subconcepts_of` | exact parent concept node ID | Direct asserted `SUBCONCEPT_OF` child edges, not transitive entailment |
| `relations_for_entity` | exact source node ID | Return outgoing relation occurrences and identities |
| `edges_by_claimed_type` | e.g. `supports` | Filter explicit, **unverified** relation-type attributes |

Each query is selected by a closed ID and receives its argument through RDFLib `initBindings` or an exact predicate whitelist. No arbitrary SPARQL, `SERVICE`, `LOAD`, update, user-defined property paths, remote access or federation.

**Correctness boundaries:** `subconcepts_of` intentionally returns direct relationships, not the G7 derived transitive closure. To inspect source-bound inferred paths use existing G7 verified services, not this index.

## Detached result guarantees

Outputs: `scientific-index.nq` and `scientific-index-report.json`. Reports include GE fingerprint, input digest, original G4 manifest hash, RI-01 N-Quads SHA-256, RI-02 N-Quads SHA-256, context identities, indexed entity/edge counts, bounded query results and explicit false authority flags. Results are sorted and serialized deterministically; the verifier regenerates the index and query result from the independently verified source and checks both bytes, parses N-Quads and validates contexts.

The detached directory must be new and outside the repository. The workflow has `contents: read` only and never commits generated RDF. GitHub Actions artifacts are temporary evidence, not durable scientific memory.

## Constraints / remaining work

- G4 canonical exporter remains the canonical byte-level publication contract. This patch is a **read-only enrichment**, not an RDF exporter rewrite.
- No SHACL engine, unrestricted SPARQL endpoint, RDF storage backend or JSON-LD remote context loading is introduced.
- No claim that RDFLib outperforms NetworkX/igraph or can replace graph algorithms.
- Exact-native G4 integration and full-regression acceptance are required on the current GitHub branch because the locally uploaded Oct. 13 repository ZIP predates G4.5.
- RDFLib 7.x deprecation warnings from older RI-01 internals are not addressed here; changing previously accepted code without current-branch baseline would raise risk.

## Acceptance requirements

1. Dispatcher profile `G8.3`: all targeted tests and full regression pass.
2. RI-02 workflow: authentic G4 export/roundtrip test runs without skipping; detached build and independent verification pass.
3. Persisted GE graph: deterministic repeatability, no repository mutations, correct node/edge counts, five contexts, and valid catalog query results.
4. Test a candidate with parallel edges and citations: each occurrence remains individually queryable.
5. Recomputed detached report hashes alone cannot hide altered source; replay rejects tampering.

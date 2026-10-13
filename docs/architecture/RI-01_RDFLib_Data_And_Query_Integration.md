# RI-01 — RDFLib source-bound named datasets and bounded SPARQL

**Purpose:** extend the completed G4/G5 RDF operations while preserving GE's authoritative scientific graph and G4's byte-identical deterministic exports.

## Provenance and graph separation

The new layer first exports the source through existing G4 `export_view()`, then calls G4.6 `verify_rdf_interoperability()` before constructing any dataset. RDFLib's `Dataset` has three named graphs, all addressed by the verified GE snapshot SHA-256:

1. **asserted:** exact G4 RDF triple set, including statement reification for each edge occurrence.
2. **fields:** selected scalar fields projected as typed RDF literals (currently `name`, `statement`, `status`, `framework`, `type`, `source_id_unverified`, `claimed_relation_type`, `status_unverified`). Nested or opaque metadata stays in G4 JSON literals, and is never silently flattened.
3. **provenance:** source fingerprint, source snapshot and input digests, G4 manifest digest, optional GE-02 HEAD/generation, explicit false authority flags, and context identities.

Parallel edges remain individually queryable through G4's RDF Statements and `parallelEdgeOccurrence`. Plain RDF triples are not used to count multiedge occurrences. No RDF material is imported into the persistent state.

## Available read-only SPARQL catalog

- `nodes_by_type` (argument `ScientificConcept` or other exact recorded type)
- `edge_occurrences_by_relation` (argument `HAS_CONCEPT`, etc.)
- `nodes_by_field` (argument one of the explicitly supported field names)

All queries are fixed SELECT templates, parameter values are passed via RDFLib `initBindings`, and results are limited to 200 rows. Arbitrary SPARQL, SPARQL UPDATE, federated SERVICE, and remote context loading are not exposed. RDFLib's own security documentation warns that untrusted queries/contexts can initiate external network or file access; **if future work offers arbitrary queries, it must run in a separate OS sandbox without network/file access**.

## Canonical detached artifacts

Outputs are written *outside* the source repository to a new directory:

- `rdf-dataset.nq`: deterministic sorted, blank-node-free N-Quads generated from RDFLib terms
- `rdf-query-report.json`: canonical JSON, SHA-256 and source-bound query results

Verification recreates both artifacts independently from GE/G4 and parses the N-Quads with RDFLib. These are detached read-only evidence, not authoritative state. Dataset N-Quads and query results cannot replace the existing G4 N-Triples/Turtle canonical publications.

## Scope and limitations

No current G4/G5/GE/G7 files or workflows are modified. There is no backend selection, unrestricted OWL reasoning, SHACL engine, external SPARQL endpoint, automatic science validation or autonomous approvals. Whitelisted semantic fields are meant for interoperability; their inclusion makes no claim about truth or source verification. Full performance characterization, a resource-isolated generic SPARQL service and schema expansion require separate measured work.

## Acceptance

Run Manual Validation Dispatcher profile `G8.2`, then run RI-01 Manual RDFLib Dataset and SPARQL Catalog Review (persisted/candidate). Verify exact triple-set preservation, parallel edge counts, read-only source, identical replay, detached manifest and authority flags.

The `G8.2` identifier is only for compatibility with the existing numeric dispatcher; RI-01 is not a renaming of the closed G4/G5 milestones.

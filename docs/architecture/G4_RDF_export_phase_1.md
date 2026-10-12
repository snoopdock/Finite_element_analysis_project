# Original G4 — RDF Export, phase 1

## Position in roadmap

The GE-01 ... GE-04 detour is complete. This milestone resumes the **original**
G4 RDF Export objective, not the GE graph-engine integration work. The generic
GitHub CI profile ID is `G4.5`, because IDs `G4.1`–`G4.4` were previously used
as temporary compatibility aliases for GE milestones.

## Native graph bridge

- Input A: **verified GE-02 `.graph-state/scientific`**, via
  `PersistentDomainGraphStore.verify()` and `.current_view()`; no fabricated
  `latest.json` paths.
- Input B: repository-local **candidate scientific JSON** which passes the
  existing GE-01 scientific graph identity and reference validation.
- No new competing graph data model or background auto-commit.

Each graph node maps to an RDF resource with stable percent-encoded identity,
RDF type, original identifier, entity type, canonical-JSON attributes and
metadata. Each semantic edge creates (1) a direct RDF relation triple and
(2) a uniquely identified `rdf:Statement` reification node preserving the
complete relation, attributes, metadata and occurrence number. Identical
parallel edges collapse as direct RDF relations per RDF set semantics, but
retain independent statement resources.

Output formats: deterministic UTF-8 **N-Triples** (`semantic-graph.nt`) and
**Turtle** (`semantic-graph.ttl`, with N-Triples statements as a valid Turtle
subset). `rdf-export-manifest.json` includes content digests, graph
fingerprint, source-snapshot identity and optional persisted HEAD/generation.

The export uses a configurable namespace in a later iteration. Current
experimental URNs are local, stable structural identifiers; they do **not**
claim ownership of an official or externally registered ontology namespace.

## Boundaries and limitations

1. All exports are **read-only** and prohibit graph state mutation, automatic
   scientific approval and inferred semantic entailment.
2. SHA-256 is a content-integrity check, not cryptographic authentication.
3. Source-node metadata and scientific assertions remain unverified unless
   another explicit scientific validation process establishes otherwise.
4. No automatic network dereferencing or imports; RDF parsing/serialization
   is not OWL reasoning. This milestone is deliberately **G4 RDF**, not G5 OWL.
5. GE-04 document-section review links will require explicit, version-bound
   RDF mapping in a later G4 extension; no text-based inferred references.
6. For production exposure, URN namespace governance and triple-size budgets
   should be reviewed and pinned as published contracts.

## Manual GitHub use

1. Copy the patch's `MAIN_BRANCH/` workflow to `main`.
2. Copy all `STAGE1_SECTION_UUIDS/` files to `stage1/section-uuids`.
3. In `main`'s **Manual Validation Dispatcher** choose `G4.5`, target
   `stage1/section-uuids`, regression `profile`. This runs full regression.
4. Run **G4 Manual RDF Export and Interoperability Verification** from `main`
   with `export_mode=persisted`. Optionally test `candidate` and supply a
   repository-local scientific JSON path. Both require an explicit manual run.
5. Download the resulting RDF files and manifest. GitHub Actions artifacts
   are temporary transport; this workflow does not claim permanent archival.

## Scientific acceptance criteria

- GE-02 persisted state independently verifies prior to export;
- all source graph entities/relations are preserved structurally;
- parallel-edge reification maintains multiplicity;
- N-Triples/Turtle parse to the exact same RDF triple set;
- deterministic output and hashed provenance;
- graph and document state remain unchanged;
- project-level tests pass against current GitHub branch.

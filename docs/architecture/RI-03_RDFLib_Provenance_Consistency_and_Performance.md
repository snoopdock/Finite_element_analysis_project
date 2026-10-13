# RI-03 — Verified RDFLib Provenance, Cross-Context Consistency and Performance

**Status:** Implementation supplied for GitHub validation, not yet accepted on the live development branch.

## Placement and trust boundaries

RI-03 is a *derived, read-only* RDFLib facility. Its source is GE-02's verified
persisted snapshot, or a bounded candidate scientific graph via GE-01. Before any
RI-03 audit executes, G4 exports that graph; G4.6 re-parses and reconstructs it;
RI-01 builds three provenance-aware RDF named graphs; and RI-02 builds two
additional named graphs containing selected scientific scalar fields and a
fixed vocabulary. **No existing G4 bytes, persisted graph state, OWL ontology,
scientific document, or reasoning record is modified.**

```
verified GE-02 graph / bounded candidate
   -> canonical SemanticGraph / GE-01
   -> G4 canonical export + G4.6 independent structural verification
   -> RI-01 3 RDFLib contexts
   -> RI-02 2 additional named contexts
   -> RI-03 source-bound five-context consistency and provenance review
   -> four fixed, parameterized read-only SPARQL queries
   -> repeated build/audit/query descriptive timing observations
   -> detached N-Quads + JSON with independent reconstitution
```

RDFLib is an **interoperability/query layer, not a sixth computational graph
backend**. Parallel graph edges are still represented as **separate G4 RDF
statement occurrences**. Two equal graph relationships do not collapse into
one scientific edge or citation in RI-03 results.

## Concrete consistency checks

1. Exact G4 snapshot node membership and number of statement occurrences match
   the verified source graph; node and statement IRI identities are disjoint.
2. Every reified occurrence references present nodes and declares exactly one
   RDF statement type, ordinal and endpoints. RI-02 already independently
   reconciles exact multiset signatures with GE-01.
3. Each indexed scientific scalar value is independently re-derived from the
   original source node or the verified G4 `attributesJson` / `metadataJson`
   statement literals. Missing, extra, orphan and altered RDF index triples
   fail closed.
4. The first three RI-01 named graphs have the same RDF triples and canonical
   N-Quads as their verified source. All five graph contexts, quad counts and
   deterministic RDF bytes are checked.
5. Source input fingerprint, graph snapshot, G4 manifest provenance, projection
   counts and explicit false authority flags are checked.
6. A mismatch fails the entire report. RI-03 does **not** infer science from
   metadata flag names or from the absence of evidence.

## Four bounded provenance queries

| Catalog ID | Argument (semantic graph node ID) | Meaning |
|---|---|---|
| `sources_for_proposition` | Proposition ID | Enumerate explicit `CITES_SOURCE` edge occurrences |
| `propositions_citing_source` | Source reference ID | Enumerate citing propositions, preserving parallel citations |
| `concept_evidence_paths` | Concept ID | Join proposition→concept and proposition→source edge occurrences |
| `relations_with_unverified_support` | Node ID | Enumerate outgoing relationship occurrences with an **explicit** `scientific_support_verified=false` scalar |

All queries are fixed SELECT templates and use RDFLib `initBindings`. The
caller controls only an exact node ID and a row limit of 1–100. No arbitrary
SPARQL, SERVICE, SPARQL UPDATE, RDF remote fetch, or graph writeback is exposed.
An empty query result is not an endorsement or a statement of completeness.

**Semantics:** `CITES_SOURCE` indicates an existing citation *link*, not source
verification; `HAS_CONCEPT` indicates graph membership, not entailment. The
joined path does not imply a paper supports, corroborates, or proves the
scientific proposition. `False` metadata is simply a declared source field.

## Performance observations

RI-03 performs one warm-up and 1–7 repetitions for each of three activities:
RI-02 source-verified dataset construction, RI-03 cross-context consistency
checking and fixed RDFLib SPARQL querying. Per-activity sample nanoseconds,
median, minimum and maximum are recorded. No universal timing threshold,
backend selection or speed ranking is produced.

Measurements are environment-dependent. Re-verification checks the exact
verified graph structure, query results, canonical N-Quads, timing sample
shape and summary arithmetic; it does **not** and cannot independently
reproduce past wall-clock durations. A self-rehashed counterfeit timing
sample could pass the self-consistency check, so detached timing observations
are **not authenticated measurements** without a separately trusted run
record. GitHub workflow logs and run identifiers supply execution context.

## Security and integrity

- `ri01._safe_output` requires a fresh detached directory outside the source
  repository and refuses existing destinations or symlink paths.
- Input is bounded using established GE, G4, RI-01, RI-02 resource limits;
  reports use the existing 120-KB RI-01 report bound.
- Detached verification independently recomputes all *non-timing* fields from
  source; refuses altered or rehashed results, modified N-Quads, missing
  named contexts, forged authority flags and benchmark arithmetic changes.
- Source hashes establish consistency of content, not cryptographic
  authenticity, scientific truth, reviewer authorization or solver proof.
- RI-03 is not an RDF/OWL reasoner or SHACL replacement.

## Pytest warning regression repair

RI-02's `test_report_digest_and_detached_roundtrip` previously returned a
4-tuple after its assertions. pytest ignores such return values and warns
`PytestReturnNotNoneWarning`. The revision removes the returned tuple and adds
explicit checks of both detached files and query cardinality. The RI-03 manual
workflow runs this test module with `PytestReturnNotNoneWarning` converted to
an error. No RI-02 production module changes are required.

The separate RDFLib `Dataset.default_context` warning seen in previous logs
is generated in the current RDFLib processing stack, not by an explicit
`default_context` call in RI-01 or RI-02. RI-03 itself uses `Dataset.graph()`
and `Dataset.quads()`; do not silence library warnings globally. Review
compatibility when upgrading pinned RDFLib versions and run full regression.

## Manual-only GitHub acceptance

1. Install `G8.4.yaml`, the new module and tests and replace the single RI-02
   test file per `PATCH_MAP.md` on `stage1/section-uuids`.
2. Add the new `ri03_manual_rdflib_provenance_audit.yml` on `main`.
3. Run existing Manual Validation Dispatcher (`branch=stage1/section-uuids`,
   `profile=G8.4`, `regression_mode=profile`). No push trigger is added.
4. Run **RI-03 Manual RDFLib Provenance, Consistency and Performance Review**
   with `source_mode=persisted`, query
   `relations_with_unverified_support`, argument
   `scientific:concept:00000000-0000-0000-0000-000000000002`, repeats `3`.
   This persisted demonstration typically has a single explicitly false
   support declaration, if its GE-02 state is unchanged.
5. Confirm source replay, authority checks, native G4 tests and artifact
   publication. The live GitHub full regression is required for acceptance.

**Older snapshot limitation:** The local October 13 development archive
predates G4.5/G4.6; the local fixture exercises the RI-02 API contract and
native G4 integration is an explicit skip. On the current branch the real G4
module must exist and the same tests must run without this skip.

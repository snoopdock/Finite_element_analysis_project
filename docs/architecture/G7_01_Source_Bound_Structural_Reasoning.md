# G7.1 — Source-Bound Structural Reasoning

## Position

Original G7 begins after G6 benchmark acceptance. This module is additive to
`core.semantic_graph`, the established G3 verification and audit rules, GE-01/02
projections and history, and G4/G5 RDF/OWL layers. None is replaced.

## Precisely defined rules

**G7.R1 (transitive concept hierarchy):** If `A SUBCONCEPT_OF B` and
`B SUBCONCEPT_OF C`, report `A SUBCONCEPT_OF C` as a structural inference
with a witnessed path, unless that exact edge already appears directly.

**G7.R2 (proposition ancestor association):** If `P HAS_CONCEPT A` and
`A SUBCONCEPT_OF ... SUBCONCEPT_OF Z` along ≥1 hierarchy step, report
`P HAS_ANCESTOR_CONCEPT Z` as a derived structural association. This is
**not** an inherited citation, scientific support or proof that P is true.

The rules operate only over `ScientificConcept` and `ScientificProposition`
GE-01 node types. `SCIENTIFIC_RELATION`, `CITES_SOURCE`, `CITES_STRUCTURALLY`
and all other graph edges are **not** eligible for these rules.

## Witnesses and verification

Every derived record identifies the source/target, rule ID, full graph path,
and the SHA-256 of every exact supporting source edge including attributes
and metadata. Source identifiers and fingerprints are bound to the GE-01
snapshot, and (for persisted mode) the verified GE-02 HEAD receipt. A second
verification command reopens the source and regenerates **every** inference
and witness; rehashing a forged report cannot fool it.

The algorithm detects cycles rather than silently collapsing them. It bounds
node count, edge occurrences, total path hops, report bytes, and inferred facts.
An over-budget source is rejected rather than returning incomplete closure.
Parallel input edge occurrences are allowed; the canonical witness is selected
reproducibly, and derived logical facts are de-duplicated.

## Authority boundary

This finite rule set is *not* unrestricted Datalog, OWL 2 reasoning, scientific
entailment, proof of correctness, executable code changes, or approval. The
report's authority flags are all false. No graph, model, document, or
repository file is written by the reasoner; only an explicitly detached
output report is created with exclusive-create semantics.

## Acceptance gate

1. `G7.1` full manual dispatcher profile passes targeted and full regression.
2. Standalone manual reasoning workflow passes tests, `run` and independent
   `verify` using the persisted verified GE-02 graph.
3. Candidate mode is exercised on the versioned demo scientific graph.
4. Adversarial tests cover cycles, wrong types, unauthorized flags,
   forged/rehashed witnesses, changed source, resource exhaustion,
   deterministic ordering, and report overwrite protection.

G7 remains open after G7.1: later reasoning functionality requires explicit
scientific semantics and evidence scope and must not be implied by these two
structural rules.

# G7.3 — Explicit reasoning-to-document acceptance

**Roadmap:** original G7 Semantic Reasoning Rules, final acceptance gate. G7.3 builds on G7.1, G7.2, GE-02/GE-03 and GE-04; it **does not** rename, supersede or reopen original G4 RDF / G5 OWL / G6 benchmarking.

## Problem and intended trust boundary

A graph can change and invalidate a previously inferred relationship while a scientific document still describes that relationship. GE-04 links **nodes** to document sections, but nodes are not the same as an inference; a node-only link cannot establish that a section relies on a specific derived relationship. G7.3 introduces editor-declared links from the **complete inferred-fact identity** (`rule_id`, `source_id`, `inferred_relation`, `target_id`) to stable section UUIDs. It never infers editorial links from text proximity, keywords, graph ancestry or document similarity.

The module recomputes GE-02 history and G7.1 closure through G7.2, rejects stale graph/document bindings, then creates detached review plans for **added, retracted and re-witnessed** inferences. The exact before/after witnessed proofs are hashed into every trigger. Distinct structures can support the same fact; G7.2 classifies proof changes separately from retractions, and G7.3 preserves that distinction.

## Versioned input contract

`g7-explicit-inference-section-bindings/v1` requires:

- `document_id`: canonical persisted UUID;
- `document_sha256`: SHA-256 of the exact persisted document JSON bytes;
- `expected_store_head_sha256`: verified GE-02 store head;
- `expected_before_snapshot_sha256` and `expected_after_snapshot_sha256`: independently reconstructed graph snapshots;
- `links`: entries with existing `section_id`, exact `fact` identity, fixed relation `EXPLICITLY_REVIEWS_INFERENCE`, and a meaningful editor-authored `rationale`.

A link may reference an inference **in the changed event set** only. Forged or stale fact identities and references to unchanged inferences are rejected. Empty or partially populated link sets generate `blocked_no_explicit_inference_mapping` or `partial_inference_mapping_requires_review`; neither is a completed acceptance outcome.

## Deterministic read-only results

`g7-reasoning-document-review/v1` contains input hashes, verified GE-02 head, source G7.2 report SHA-256, before/after snapshot IDs, exact add/retract/re-witness event counts, section-review tasks, unmapped inference events, and a canonical report digest. The independent `verify` command **replays from the graph/document inputs**, not from a trusted JSON manifest alone.

The source and review policies prohibit automated scientific approval, OWL DL entailment claims, factual truth claims, graph mutation and document editing. Inference retraction means **loss of support under the bounded structural rule set**, not scientific disproof.

## Demo / manual workflow

The demo uses the actual GE-02 persisted graph, G7.2 reparented candidate (`examples/graph_engine/g72_demo_reparented_graph.json`), persisted GE-04 document (`examples/graph_engine/ge04_demo_document.json`), and G7.3 explicit inference links (`examples/graph_engine/g73_demo_inference_section_bindings.json`). The fixed GE-02 generation-1 head yields one added inference and one retraction mapped to two section UUIDs. If the checked-out GE-02 head or demonstration document changes, **regenerate and manually review the binding file**; bypassing the version check is forbidden.

The workflow `G7.3 Manual Reasoning-to-Document Acceptance` is `workflow_dispatch` only with read-only permissions and separate checkout. Default `require_complete_mapping=true` fails acceptance when changed inferences remain unmapped. `latest-transition` is useful only with a binding file matching the actual historical snapshots; generation 1 correctly yields no prior transition.

The existing **Manual Validation Dispatcher** is separately run with profile `G7.3` and regression mode `profile`; it must pass before G7 can be declared closed.

## G7 closure criteria

1. G7.1 deterministic witnessed structural inference independently verified.
2. G7.2 added / retracted / re-witnessed lifecycle independently verified, including no-prior-transition behavior.
3. G7.3 explicitly grounded inference-change → document-section review, including completeness gate and safe failure behavior.
4. G7.3 GitHub targeted test suite, full regression, and detached manual workflow pass with source-bound integrity and provenance.
5. No scientific approval, automatic document mutation, external OWL reasoner equivalence or formal proof of textual scientific correctness is asserted.

**Do not mark G7 closed based solely on this patch's local tests.** Close it only after the two GitHub G7.3 workflows satisfy the above criteria.

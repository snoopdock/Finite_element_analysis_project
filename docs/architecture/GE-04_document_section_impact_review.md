# GE-04 — Verified Graph-to-Document Impact Planning

## Purpose

GE-01 builds typed graph identities, GE-02 stores and verifies content-addressed graph versions, and GE-03 computes bounded structural review candidates for a real proposed or committed graph change. GE-04 closes the next operational gap: explicitly associate scientific nodes with existing, UUID-identified **semantic document sections**, then generate a **read-only, human-review-required plan** identifying sections that may be affected.

This **does not establish scientific truth**, update documents, approve revisions, infer citations from prose, or modify the GE-02 store. The original roadmap's **G4 — RDF Export** is separate; the compatibility validation profile is `G4.4` only because the existing dispatcher expects numeric `G` profiles.

## Design and data contracts

- **Graph:** GE-03 `analyze()` verifies the complete GE-02 commit/snapshot chain and uses native delta/propagation APIs. No new graph solver is implemented.
- **Document:** A persisted `core.document_model.Document` with the correct schema version, canonical stable `document_id` and `section_id` UUIDs. The system never silently creates missing IDs. `core.document_persistence.save_document()` can produce the required JSON.
- **Explicit bindings:** `ge04-explicit-section-bindings/v1` links individual `section_id`s and scientific graph node IDs. Each relationship uses `EXPLICITLY_REFERENCES` and includes a rationale. This is a structural relationship, not a truth claim. The manifest binds the document's exact file SHA-256, the verified GE-02 HEAD, and the compared candidate snapshot SHA-256. The manifest must be updated after intentional changes to these inputs.
- **Review plan:** `ge04-bound-section-review-plan/v1` contains source digests, graph provenance, affected section UUIDs, triggering graph nodes, structural distances, and explicit unmapped nodes. Its canonical SHA-256 is independently verified by the manual GitHub workflow.

Example binding entry:

```json
{"section_id":"10000000-0000-0000-0000-000000000001",
 "graph_node_id":"scientific:concept:00000000-0000-0000-0000-000000000001",
 "relation":"EXPLICITLY_REFERENCES",
 "rationale":"Editorially established link from this section to the scientific concept"}
```

## Operation

Apply files according to the patch map. Start **Manual Validation Dispatcher** from `main`, with branch `stage1/section-uuids`, profile **`G4.4`** and regression mode `profile`.

For the functional demo, start **GE-04 Manual Scientific Document Impact Review** from `main`, choose:

- `branch`: `stage1/section-uuids`
- `mode`: `candidate`
- `knowledge_graph_path`: `examples/graph_engine/ge03_demo_changed_graph.json`
- `document_path`: `examples/graph_engine/ge04_demo_document.json`
- `bindings_path`: `examples/graph_engine/ge04_demo_section_bindings.json`

The expected **demonstration-only** result is three graph review candidates, explicitly mapped to two sections. It is not a test of the scientific validity of the provided proposition.

For actual FEM documents, first persist the **semantic document model** with stable UUIDs, explicitly curate the graph-to-section references, and bind the file and graph fingerprints. Legacy `output/sections.json` records lacking section IDs cannot be treated as validated bindings. An inferred mapping from free-text section content is expressly prohibited.

`latest-transition` requires a corresponding bindings manifest with `expected_compared_snapshot_sha256: null` when generation 1 has no prior transition, or the exact compared snapshot hash when a verified later transition exists.

## Status and safety policies

- `review_plan_ready`: every GE-03 structural review candidate has at least one explicit section link.
- `partial_mapping_requires_review`: some review candidates have no explicitly linked section; these IDs remain visible in `unmapped_graph_node_ids`.
- `blocked_no_section_mapping`: no review candidates have a linked section.
- `no_change_to_review`: GE-03 reports no graph change or no prior transition.

Even a `review_plan_ready` result **does not authorize edits**. The user or an approved future SAT planning layer can inspect the proposals and request independent scientific verification. All results are read-only and deterministically hashed. SHA-256 is integrity checking, not independent authorship certification.

## Future boundary

This patch establishes a verified, explicit *scientific-graph-to-document-section* bridge. It does not yet infer impact on FEM executable solver modules or automatically create justified bindings. Those are separate future capabilities and must require independent evidence and authorization.

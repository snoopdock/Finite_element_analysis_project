# GE-01 — Graph identity and domain integration

Status: **implementation candidate, pending manual GitHub CI**.

## Why GE-01

The project already contains `SemanticGraph`, `SemanticGraphAnalysisService`,
`GraphTraversalEngine`, NetworkX/SciPy backend adapters, a UUID-keyed scientific
knowledge graph (`core.knowledge_graph`), and a read-only typed projection from
G3.5's generated-text assurance pipeline. This implementation **does not**
replace or reimplement any of them. It creates a strict, read-only bridge from
two existing domains into the canonical graph, and reuses its analysis engine.

## Domain mapping

| Source record | Node type | Stable node ID |
|---|---|---|
| `concepts[concept_uuid]` | `ScientificConcept` | `scientific:concept:<uuid>` |
| `propositions[proposition_uuid]` | `ScientificProposition` | `scientific:proposition:<uuid>` |
| `source_ids` | `ScientificSourceRef` | `scientific:source:sha256(identifier)` |
| Verified G3.5 memory record | `AuditMemoryRecord` | `audit:memory:<record id>` |
| Verified G3.5 generated claim | `AuditGeneratedClaim` | `audit:claim:<index>:<sha256>` |

Scientific source identifiers are opaque until checked by a separate source
resolver. A SHA-256 ID is an **identifier binding**, not scientific verification.

Typed relationships from the scientific domain:
`SUBCONCEPT_OF`, `HAS_CONCEPT`, `CITES_SOURCE`, `SCIENTIFIC_RELATION`,
`RELATION_ASSERTED_BY`. The original claimed relation type stays an unverified
attribute of `SCIENTIFIC_RELATION`. G3.5 yields `CITES_STRUCTURALLY`, never
`SUPPORTED_BY` or `PROVES`. **Neither graph is an authoritative proof graph.**

## Integrity and deterministic identity

- Every UUID is canonical and matches its enclosing map key.
- Dangling UUID references are rejected through `validate_graph_references`.
- Duplicate source IDs and malformed graph collections fail closed.
- Domain snapshot and fingerprint are deterministic under insertion reordering.
- Projection copies input records, does not update the underlying graph state,
  and generates no decision or authorization.
- G3.5 cycles are independently reverified against source files using
  `assurance_integration.verify_cycle` before projection; review-dependent
  cycles require the original review submission and actor.
- Disjoint domain union rejects collisions instead of silently merging
  similarly named scientific and audit entities.
- `verify_snapshot` compares the entire snapshot against an independently
  projected view. Merely recomputing a checksum on forged content is rejected.
- CLI refuses symlink JSON inputs and writing inside the repository.

## Usage in GitHub Actions

Apply the files to `stage1/section-uuids`. Use the **existing** workflow on
`main`: `Manual Validation Dispatcher`, branch `stage1/section-uuids`, profile
`GE-01`, regression mode `profile`.

No new workflow file or push trigger is needed. GitHub performs full regression
and publishes its temporary evidence artifact as before.

An optional **read-only** command, usable from a local checkout or a manually
started GitHub job, accepts an existing knowledge graph snapshot and optionally
a G3.5 audit record:

```sh
python -m audit_engine.semantic_audit.graph.domain_integration \
  --repository . \
  --knowledge-graph /tmp/knowledge_graph.json \
  --output /tmp/ge01_graph.json
```

To include G3.5 citations, also supply `--g35-cycle /tmp/cycle.json`.
The cycle **must** verify against the chosen checkout. The CLI outputs graph
observations, not permission to edit sections or publish claims.

## GE-01 acceptance / GE-02 handoff

Acceptance requires (1) existing G3.5 semantics retained, (2) stable scientific
identity and reference integrity, (3) existing graph query engine compatibility,
(4) negative mutation/tampering tests, (5) full branch regression.

GE-02 can then add incremental updates, dependency invalidation, persistence and
atomic graph snapshots using this stable projection boundary; it should not
assume that `GE-01` already provides durable storage or automatic decision
execution.

## Provenance limitations

The last known repository snapshot used for local testing predates recent
G3.x patches. Later branch-side patch files were layered in to reconstruct the
interfaces. The **current GitHub branch** is the source of truth for acceptance.

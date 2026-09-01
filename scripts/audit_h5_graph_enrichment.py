#!/usr/bin/env python3
"""Audit preservation of enriched scientific collections through graph normalization."""

from copy import deepcopy

from core.knowledge_graph import normalize_graph, validate_graph_references


def main() -> int:
    concept_id = "11111111-1111-4111-8111-111111111111"
    proposition_id = "22222222-2222-4222-8222-222222222222"
    relationship_id = "33333333-3333-4333-8333-333333333333"

    graph = {
        "concepts": {
            concept_id: {
                "concept_id": concept_id,
                "name": "Finite element method",
                "type": "method",
                "source_ids": ["s-001"],
            }
        },
        "propositions": {
            proposition_id: {
                "proposition_id": proposition_id,
                "statement": "Method A converges under coercivity.",
                "concept_ids": [concept_id],
                "source_ids": ["s-001"],
                "context": {
                    "framework": "Galerkin FEM",
                    "conditions": ["coercive operator"],
                    "domain_of_validity": ["elliptic PDE"],
                },
                "validity_scope_ids": ["v-001"],
                "assertion_ids": ["a-001"],
                "epistemic_state_id": "p-001",
                "perspective_signature_id": "perspective-001",
            }
        },
        "relationships": {
            relationship_id: {
                "relationship_id": relationship_id,
                "source_id": concept_id,
                "target_id": proposition_id,
                "type": "related_to",
                "proposition_ids": [proposition_id],
            }
        },
        "evidence_relations": {"er-001": {"source_id": "s-001", "proposition_id": proposition_id}},
        "validity_scopes": {"v-001": {"validity_id": "v-001", "proposition_id": proposition_id}},
        "assertions": {"a-001": {"assertion_id": "a-001", "proposition_id": proposition_id}},
        "epistemic_states": {f"proposition:{proposition_id}": {"entity_id": proposition_id}},
        "perspective_signatures": {"perspective-001": {"signature_id": "perspective-001", "proposition_ids": [proposition_id]}},
    }

    original = deepcopy(graph)
    normalize_graph(graph)

    # Core graph entities must survive normalization.
    assert concept_id in graph["concepts"]
    assert proposition_id in graph["propositions"]
    assert relationship_id in graph["relationships"]

    # Proposition scientific context must survive normalization.
    proposition = graph["propositions"][proposition_id]
    assert proposition["context"]["framework"] == original["propositions"][proposition_id]["context"]["framework"]
    assert proposition["validity_scope_ids"] == ["v-001"]
    assert proposition["assertion_ids"] == ["a-001"]
    assert proposition["epistemic_state_id"] == "p-001"
    assert proposition["perspective_signature_id"] == "perspective-001"

    # Current normalizer is allowed to preserve unknown top-level collections.
    for key in ("evidence_relations", "validity_scopes", "assertions", "epistemic_states", "perspective_signatures"):
        assert key in graph, f"normalized graph dropped collection: {key}"

    assert validate_graph_references(graph) == []

    print("H5 graph enrichment audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

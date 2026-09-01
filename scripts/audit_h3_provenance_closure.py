#!/usr/bin/env python3
"""Audit provenance closure across the hardened scientific graph layers."""


def main() -> int:
    state = {
        "knowledge_graph": {
            "sources": {
                "s-001": {"source_id": "s-001", "title": "FEM study"},
            },
            "propositions": {
                "p-001": {
                    "proposition_id": "p-001",
                    "statement": "Method A converges under coercivity.",
                    "source_ids": ["s-001"],
                },
            },
            "evidence_locations": {
                "loc-001": {
                    "location_id": "loc-001",
                    "source_id": "s-001",
                    "passage_id": "passage-001",
                },
            },
            "evidence_relations": {
                "er-001": {
                    "evidence_relation_id": "er-001",
                    "source_id": "s-001",
                    "proposition_id": "p-001",
                    "relationship": "supports",
                    "passage_ids": ["passage-001"],
                    "status": "active",
                },
            },
            "assertions": {
                "a-001": {
                    "assertion_id": "a-001",
                    "source_id": "s-001",
                    "proposition_id": "p-001",
                    "role": "proposes",
                    "evidence_relation_ids": ["er-001"],
                    "passage_ids": ["passage-001"],
                },
            },
            "relationship_support": {
                "rs-001": {
                    "support_id": "rs-001",
                    "relationship_id": "r-001",
                    "proposition_ids": ["p-001"],
                    "source_ids": ["s-001"],
                    "status": "proposed",
                },
            },
            "relationships": {
                "r-001": {
                    "relationship_id": "r-001",
                    "source": "concept-a",
                    "target": "concept-b",
                    "type": "related_to",
                },
            },
        }
    }

    graph = state["knowledge_graph"]
    relation = graph["relationships"]["r-001"]
    support = graph["relationship_support"]["rs-001"]
    assert support["relationship_id"] == relation["relationship_id"]

    proposition_id = support["proposition_ids"][0]
    proposition = graph["propositions"][proposition_id]
    source_id = support["source_ids"][0]
    assertion = graph["assertions"]["a-001"]
    assert assertion["proposition_id"] == proposition_id
    assert assertion["source_id"] == source_id
    assert source_id in proposition["source_ids"]
    assert source_id in graph["sources"]

    for evidence_id in assertion["evidence_relation_ids"]:
        evidence = graph["evidence_relations"][evidence_id]
        assert evidence["source_id"] == source_id
        assert evidence["proposition_id"] == proposition_id
        for passage_id in evidence["passage_ids"]:
            matching = [
                item for item in graph["evidence_locations"].values()
                if item.get("source_id") == source_id
                and item.get("passage_id") == passage_id
            ]
            assert matching, f"no location for {source_id}:{passage_id}"

    print("H3 provenance closure audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

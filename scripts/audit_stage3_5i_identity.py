#!/usr/bin/env python3
"""Runtime-ready audit for Stage 3.5I evidence-relation identity."""

from __future__ import annotations

from analysis.evidence_relation_identity import (
    deduplicate_evidence_relations,
    evidence_relation_id,
    normalize_evidence_relation_identity,
)


def main() -> int:
    first = evidence_relation_id("S1", "P1", "supports", ["L2", "L1"])
    second = evidence_relation_id("S1", "P1", "supports", ["L1", "L2"])
    assert first == second

    relation = {
        "source_id": "S1",
        "proposition_id": "P1",
        "relationship": "SUPPORTS",
        "passage_ids": ["L2", "L1", "L1"],
        "reason": "direct evidence",
    }
    normalized = normalize_evidence_relation_identity(relation)
    assert normalized["relationship"] == "supports"
    assert normalized["passage_ids"] == ["L1", "L2"]
    assert normalized["evidence_relation_id"] == first

    duplicate = dict(relation)
    duplicate["reason"] = "same relation, updated wording"
    result = deduplicate_evidence_relations([relation, duplicate])
    assert len(result) == 1
    assert result[0]["reason"] == "same relation, updated wording"

    distinct_passage = dict(relation)
    distinct_passage["passage_ids"] = ["L3"]
    result = deduplicate_evidence_relations([relation, distinct_passage])
    assert len(result) == 2

    print("Stage 3.5I identity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

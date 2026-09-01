#!/usr/bin/env python3
"""Combined runtime-ready checkpoint audit for Stage 3.5 evidence hardening."""

from __future__ import annotations

from analysis.evidence_relation_identity import deduplicate_evidence_relations
from analysis.evidence_relation_integrity import validate_evidence_relation


def main() -> int:
    relation = {
        "source_id": "S1",
        "proposition_id": "P1",
        "relationship": "supports",
        "passage_ids": ["L1"],
        "classification_confidence": 0.8,
        "reason": "The cited passage directly addresses the proposition.",
    }
    normalized = deduplicate_evidence_relations([relation])[0]
    errors = validate_evidence_relation(
        normalized,
        source_ids=["S1"],
        proposition_ids=["P1"],
        location_ids=["L1"],
    )
    assert not errors, errors
    assert normalized["evidence_relation_id"].startswith("evidrel-")
    assert "verified" not in normalized
    assert "verification_status" not in normalized

    bad = dict(normalized)
    bad["verification_status"] = "verified"
    assert validate_evidence_relation(
        bad,
        source_ids=["S1"],
        proposition_ids=["P1"],
        location_ids=["L1"],
    )

    duplicate = dict(relation)
    duplicate["reason"] = "updated assessment for same source/proposition/passage"
    result = deduplicate_evidence_relations([relation, duplicate])
    assert len(result) == 1
    assert result[0]["reason"] == duplicate["reason"]

    print("Stage 3.5 final audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

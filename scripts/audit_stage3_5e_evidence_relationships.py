#!/usr/bin/env python3
"""Read-only audit for Stage 3.5E evidence-proposition relationships."""

from __future__ import annotations

from analysis.evidence_relationships import (
    evidence_relation_id,
    make_evidence_relation,
    normalize_evidence_relation,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    source_id = "source-001"
    proposition_id = "prop-001"

    first_id = evidence_relation_id(source_id, proposition_id)
    second_id = evidence_relation_id(source_id, proposition_id)
    check(first_id == second_id, "Evidence relation identity is not deterministic")

    relation = make_evidence_relation(
        source_id,
        proposition_id,
        {
            "relationship": "supports",
            "classification_confidence": 0.91,
            "passage_ids": ["passage-7", "passage-7"],
            "reason": "The reported result directly bears on the proposition.",
        },
        provenance={
            "created_by": "test",
            "created_at": "2026-09-01T00:00:00Z",
            "method": "stub",
        },
    )

    check(relation["evidence_relation_id"] == first_id, "Stable identity mismatch")
    check(relation["source_id"] == source_id, "Source provenance lost")
    check(relation["proposition_id"] == proposition_id, "Proposition identity lost")
    check(relation["relationship"] == "supports", "Relationship type not normalized")
    check(relation["passage_ids"] == ["passage-7"], "Passage IDs were not deduplicated")
    check(0.0 <= relation["classification_confidence"] <= 1.0, "Confidence out of bounds")
    check(relation["status"] == "assessed", "Evidence relation should not imply verification")
    check("verified" not in relation, "Evidence relation incorrectly implies verification")

    bad = normalize_evidence_relation({"relationship": "verified_true", "classification_confidence": "bad"})
    check(bad["relationship"] == "unknown", "Invalid relationship was not downgraded to unknown")
    check(bad["classification_confidence"] == 0.0, "Invalid confidence did not degrade to zero")

    print("Stage 3.5E evidence-relationship audit: PASS")


if __name__ == "__main__":
    main()

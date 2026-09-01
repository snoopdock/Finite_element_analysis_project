#!/usr/bin/env python3
"""Runtime-ready audit for Stage 3.5H evidence-relation integrity."""

from __future__ import annotations

import copy

from analysis.evidence_relation_integrity import validate_evidence_relation


def main() -> int:
    sources = ["S1"]
    propositions = ["P1", "P2"]
    locations = ["L1"]
    relation = {
        "evidence_relation_id": "ER1",
        "source_id": "S1",
        "proposition_id": "P1",
        "relationship": "supports",
        "classification_confidence": 0.9,
        "passage_ids": ["L1"],
        "reason": "The source directly derives the stated result.",
    }
    before = copy.deepcopy(relation)
    errors = validate_evidence_relation(
        relation,
        source_ids=sources,
        proposition_ids=propositions,
        location_ids=locations,
    )
    assert not errors, errors
    assert relation == before

    bad = dict(relation)
    bad["verification_status"] = "verified"
    assert validate_evidence_relation(
        bad,
        source_ids=sources,
        proposition_ids=propositions,
        location_ids=locations,
    )

    bad_location = dict(relation)
    bad_location["passage_ids"] = ["UNKNOWN"]
    assert validate_evidence_relation(
        bad_location,
        source_ids=sources,
        proposition_ids=propositions,
        location_ids=locations,
    )

    print("Stage 3.5H integrity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

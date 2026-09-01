#!/usr/bin/env python3
"""Combined source-level/runtime-ready audit for Stage 3.5 evidence hardening."""

from __future__ import annotations

from analysis.evidence_characterization import normalize_characterization
from analysis.evidence_locations import make_evidence_location
from analysis.evidence_relationships import make_evidence_relation
from analysis.evidence_relation_policy import validate_evidence_relation_for_retention


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    characterization = normalize_characterization(
        {
            "publication_status": "peer_reviewed",
            "study_type": "theoretical",
            "evidence_role": "establishes",
            "replication_status": "not_applicable",
            "limitations": ["limited to coercive operators"],
        }
    )
    check(characterization["publication_status"] == "peer_reviewed", "Characterization lost publication status")
    check(characterization["study_type"] == "theoretical", "Characterization lost study type")
    check(characterization["replication_status"] == "not_applicable", "Characterization lost replication state")

    location = make_evidence_location(
        "source-001",
        {"section_type": "results", "page": 12, "char_start": 100, "char_end": 220, "passage_id": "p-1"},
    )
    check(location["evidence_location_id"].startswith("loc-"), "Location identity missing")
    check(location["source_id"] == "source-001", "Location provenance lost")

    relation = make_evidence_relation(
        "source-001",
        "prop-001",
        {
            "relationship": "supports",
            "classification_confidence": 0.82,
            "passage_ids": [location["evidence_location_id"]],
            "reason": "The passage reports the relevant convergence result.",
        },
        provenance={
            "created_by": "stage3_5_audit",
            "created_at": "2026-09-01T00:00:00Z",
            "method": "stub",
        },
    )
    diagnostics = validate_evidence_relation_for_retention(relation)
    check(diagnostics["valid"], "Valid evidence relation failed retention validation")
    check(diagnostics["state"] == "supporting", "Supporting state was not retained")
    check(not diagnostics["is_verification_assertion"], "Evidence relation became verification")
    check(relation["source_id"] == "source-001", "Evidence source identity lost")
    check(relation["proposition_id"] == "prop-001", "Evidence proposition identity lost")
    check(relation["passage_ids"] == [location["evidence_location_id"]], "Evidence location linkage lost")

    challenged = make_evidence_relation(
        "source-002",
        "prop-001",
        {"relationship": "challenges", "classification_confidence": 0.73},
    )
    check(validate_evidence_relation_for_retention(challenged)["state"] == "challenging", "Challenge state missing")

    neutral = make_evidence_relation(
        "source-003",
        "prop-001",
        {"relationship": "does_not_address"},
    )
    check(validate_evidence_relation_for_retention(neutral)["state"] == "non_evidence", "Neutral evidence state missing")

    contaminated = dict(relation)
    contaminated["verified"] = True
    check(
        not validate_evidence_relation_for_retention(contaminated)["valid"],
        "Verification marker incorrectly accepted on evidence relation",
    )

    print("Stage 3.5 combined audit: PASS")


if __name__ == "__main__":
    main()

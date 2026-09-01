#!/usr/bin/env python3
"""Read-only audit for Stage 3.5G evidence-relation policy."""

from __future__ import annotations

from analysis.evidence_relation_policy import (
    evidence_relation_state,
    is_verification_assertion,
    validate_evidence_relation_for_retention,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    cases = {
        "supports": "supporting",
        "challenges": "challenging",
        "qualifies": "qualifying",
        "provides_context_for": "contextual",
        "reproduces": "reproducing",
        "does_not_address": "non_evidence",
        "unknown": "unresolved",
    }

    for relationship, expected in cases.items():
        check(
            evidence_relation_state({"relationship": relationship}) == expected,
            f"Unexpected retention state for {relationship}",
        )

    relation = {
        "source_id": "source-001",
        "proposition_id": "prop-001",
        "relationship": "supports",
        "classification_confidence": 0.9,
    }
    result = validate_evidence_relation_for_retention(relation)
    check(result["valid"], "Valid evidence relation was rejected")
    check(result["state"] == "supporting", "Supporting state was not preserved")
    check(not result["is_verification_assertion"], "Evidence support became verification")
    check(not is_verification_assertion(relation), "Evidence relation incorrectly reports verification")

    invalid = validate_evidence_relation_for_retention({"relationship": "supports"})
    check(not invalid["valid"], "Missing identities were accepted")
    check("missing source_id" in invalid["issues"], "Missing source was not diagnosed")
    check("missing proposition_id" in invalid["issues"], "Missing proposition was not diagnosed")

    contaminated = validate_evidence_relation_for_retention(
        {
            "source_id": "source-001",
            "proposition_id": "prop-001",
            "relationship": "supports",
            "verified": True,
        }
    )
    check(not contaminated["valid"], "Verification semantics leaked into evidence relation")
    check(contaminated["is_verification_assertion"], "Explicit verification marker was not detected")

    print("Stage 3.5G evidence-policy audit: PASS")


if __name__ == "__main__":
    main()

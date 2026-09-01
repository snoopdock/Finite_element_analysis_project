#!/usr/bin/env python3
"""Read-only audit for Stage 7 concept-relationship semantic normalization."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.concept_relationship_analyzer import normalize_relationship_proposal


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        checks = {
            "subconcept": "subconcept_of",
            "specializes": "specializes",
            "generalizes": "generalizes",
            "alternative": "alternative_to",
            "alternative_to": "alternative_to",
            "complementary": "complements",
            "complements": "complements",
            "related": "related_to",
            "insufficient": "insufficient_evidence",
        }

        for raw, expected in checks.items():
            result = normalize_relationship_proposal({"relationship": raw})
            check(result["relationship"] == expected, f"{raw!r} was normalized incorrectly.")

        unknown = normalize_relationship_proposal({"relationship": "contradicts"})
        check(unknown["relationship"] == "insufficient_evidence", "Unsupported relation was accepted.")

        bounded = normalize_relationship_proposal({"confidence": -3})
        check(bounded["confidence"] == 0.0, "Lower confidence bound failed.")
        bounded = normalize_relationship_proposal({"confidence": 4})
        check(bounded["confidence"] == 1.0, "Upper confidence bound failed.")

        # The proposal normalizer produces no graph relationship or concept mutation.
        result = normalize_relationship_proposal({
            "relationship": "generalizes",
            "reason": "explicit source statement",
            "source_ids": ["source-a", "source-a", "source-b"],
        })
        check(result["source_ids"] == ["source-a", "source-b"], "Provenance normalization failed.")
        check("relationship_id" not in result, "Normalizer unexpectedly created an authoritative relationship ID.")

        print("Stage 7 semantic relationship semantics audit")
        print("===============================================")
        print("PASS: relation aliases, directional/symmetric label normalization, confidence bounds, and proposal-only behavior passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 7 SEMANTIC RELATIONSHIP SEMANTICS AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

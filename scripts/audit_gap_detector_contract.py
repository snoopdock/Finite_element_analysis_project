#!/usr/bin/env python3
"""Audit the GapDetector API expected by the research pipeline."""

from analysis.gap_detector import GapDetector, classify_knowledge_type


class StubResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def main() -> int:
    detector = GapDetector({
        "gap_detection": {
            "max_wikipedia_topics": 4,
            "max_gap_queries_per_cycle": 2,
            "min_concepts_per_topic": 2,
            "wikipedia_pages": ["Finite element method"],
        }
    })

    assert hasattr(detector, "detect_gaps")
    assert hasattr(detector, "get_gap_report")
    assert callable(detector.detect_gaps)
    assert callable(detector.get_gap_report)

    # Exercise the deterministic fallback without network/provider access.
    detector.fetch_wikipedia_taxonomy = lambda: [
        "Weak formulation",
        "Galerkin method",
        "Contact mechanics",
    ]
    missing, queries = detector.detect_gaps({
        "concepts": [{
            "name": "Galerkin method",
            "explanation": "The Galerkin formulation uses weighted residuals.",
        }]
    })
    assert isinstance(missing, list)
    assert isinstance(queries, list)
    assert len(missing) <= 2
    assert len(queries) == len(missing)
    assert isinstance(detector.get_gap_report(missing), str)

    # Preserve the separate information-type classifier API.
    assert classify_knowledge_type("a textbook-level FEM result", 3) == "general"
    assert classify_knowledge_type("we propose a new method", 1) == "novel"

    print("GapDetector contract audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

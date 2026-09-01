#!/usr/bin/env python3
"""Read-only audit for Stage 3.5A evidence characterization."""

from __future__ import annotations

from analysis.evidence_characterization import (
    attach_evidence_scope,
    characterize_source,
    normalize_evidence_characterization,
    normalize_evidence_scope,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    source = {
        "source_id": "source-001",
        "provider": "semantic_scholar",
        "source_type": "academic",
        "query_context": "finite element stability",
        "retrieved_at": "2026-09-01T00:00:00+00:00",
        "ranking": {"score": 0.91},
    }

    characterization = normalize_evidence_characterization({
        "publication_status": "peer_reviewed",
        "study_type": "theoretical",
        "evidence_role": "primary",
        "primary_or_secondary": "primary",
        "replication_status": "unknown",
        "methodological_description": "Derives a stability estimate.",
        "limitations": ["Restricted to the stated assumptions."],
    })

    check(characterization["publication_status"] == "peer_reviewed", "Publication status normalization failed.")
    check(characterization["study_type"] == "theoretical", "Study type normalization failed.")
    check(characterization["evidence_role"] == "primary", "Evidence role normalization failed.")
    check(characterization["replication_status"] == "unknown", "Replication default failed.")

    normalized = characterize_source(source, characterization=characterization)
    check(normalized["source_id"] == source["source_id"], "Source identity changed.")
    check(normalized["provider"] == source["provider"], "Provider provenance changed.")
    check(normalized["query_context"] == source["query_context"], "Query provenance changed.")
    check(normalized["ranking"] == source["ranking"], "Retrieval ranking metadata changed.")
    check(normalized["evidence_characterization"] == characterization, "Characterization was not attached as a separate object.")

    scope = normalize_evidence_scope({
        "proposition_ids": ["p1", "p2", "p1"],
        "relationships": {"p1": "supports", "p2": "challenges", "p3": "made_up"},
    })
    check(scope["proposition_ids"] == ["p1", "p2"], "Proposition IDs were not normalized deterministically.")
    check(scope["relationships"]["p1"] == "supports", "Support relationship failed.")
    check(scope["relationships"]["p2"] == "challenges", "Challenge relationship failed.")
    check(scope["relationships"]["p3"] == "unknown", "Unknown relationship was not downgraded.")

    scoped = attach_evidence_scope(source, proposition_ids=["p1"], relationships={"p1": "supports"})
    check(scoped["source_id"] == source["source_id"], "Evidence scope changed source identity.")
    check(scoped["evidence_scope"]["proposition_ids"] == ["p1"], "Evidence scope was not attached.")

    print("Stage 3.5A evidence characterization audit")
    print("===========================================")
    print("PASS: structured characterization, provenance preservation, and proposition-level evidence scope passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

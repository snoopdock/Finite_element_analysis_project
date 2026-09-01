#!/usr/bin/env python3
"""Read-only audit for Stage 3.5B evidence state persistence."""

from __future__ import annotations

from core.evidence_state import upsert_evidence_characterization, upsert_evidence_scope


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    state = {
        "evidence": [
            {
                "source_id": "source-001",
                "provider": "semantic_scholar",
                "query_context": "finite element stability",
                "ranking": {"score": 0.91},
            }
        ]
    }
    original = dict(state["evidence"][0])

    changed = upsert_evidence_characterization(
        state,
        "source-001",
        {
            "publication_status": "peer_reviewed",
            "study_type": "theoretical",
            "evidence_role": "primary",
        },
    )
    check(changed, "First characterization update was not stored.")
    check(
        state["evidence_characterization"]["source-001"]["publication_status"] == "peer_reviewed",
        "Characterization was not normalized/persisted.",
    )
    check(state["evidence"][0] == original, "Retrieval metadata was mutated by characterization state.")

    changed_again = upsert_evidence_characterization(
        state,
        "source-001",
        {
            "publication_status": "peer_reviewed",
            "study_type": "theoretical",
            "evidence_role": "primary",
        },
    )
    check(not changed_again, "Identical characterization update was not idempotent.")

    scope_changed = upsert_evidence_scope(
        state,
        "source-001",
        proposition_ids=["p1", "p2", "p1"],
        relationships={"p1": "supports", "p2": "challenges"},
    )
    check(scope_changed, "First evidence-scope update was not stored.")
    scope = state["evidence_scope"]["source-001"]
    check(scope["proposition_ids"] == ["p1", "p2"], "Evidence-scope proposition IDs were not normalized.")
    check(scope["relationships"]["p1"] == "supports", "Evidence-scope support relation missing.")

    check(upsert_evidence_characterization(state, "source-002", {}) is True,
          "Independent source characterization was not stored.")
    check("source-002" in state["evidence_characterization"], "Second source key missing.")
    check("source-001" in state["evidence_characterization"], "First source key was lost.")

    print("Stage 3.5B evidence state audit")
    print("================================")
    print("PASS: isolated persistence, idempotence, source-key separation, and retrieval-metadata preservation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

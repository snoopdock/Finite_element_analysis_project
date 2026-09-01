#!/usr/bin/env python3
"""Combined audit for Stage 5.5 perspective signatures."""

from analysis.perspective_signature import signature_from_propositions
from core.perspective_signature_state import record_perspective_signature


def main() -> int:
    propositions = [
        {
            "proposition_id": "P1",
            "statement": "Method A is stable.",
            "framework": "Framework F",
            "assumptions": ["A1"],
            "method": "Method M",
            "domain_of_validity": "Domain D",
            "source_ids": ["S1"],
        },
        {
            "proposition_id": "P2",
            "statement": "Method A has a limited regime.",
            "framework": "Framework F",
            "assumptions": ["A2"],
            "method": "Method M",
            "domain_of_validity": "Domain D",
            "source_ids": ["S2"],
        },
    ]
    signature = signature_from_propositions(propositions)
    assert signature is not None
    assert signature["framework"] == "Framework F"
    assert set(signature["proposition_ids"]) == {"P1", "P2"}

    state = {"knowledge_graph": {}}
    assert record_perspective_signature(state, signature)
    saved = state["knowledge_graph"]["perspective_signatures"][signature["signature_id"]]
    assert saved["source_ids"] == ["S1", "S2"]
    assert "verified" not in saved
    assert "truth" not in saved

    print("Stage 5.5 combined audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

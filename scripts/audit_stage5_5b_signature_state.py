#!/usr/bin/env python3
"""Audit persistence of derived perspective signatures."""

from core.perspective_signature_state import record_perspective_signature, record_perspective_signatures


def main() -> int:
    state = {"knowledge_graph": {}}
    signature = {
        "signature_id": "perspective-1",
        "framework": "Galerkin FEM",
        "proposition_ids": ["P1"],
        "source_ids": ["S1"],
    }
    assert record_perspective_signature(state, signature)
    assert state["knowledge_graph"]["perspective_signatures"]["perspective-1"]["framework"] == "Galerkin FEM"
    assert record_perspective_signature(state, dict(signature, framework="Galerkin FEM v2"))
    assert state["knowledge_graph"]["perspective_signatures"]["perspective-1"]["framework"] == "Galerkin FEM v2"

    count = record_perspective_signatures(
        state,
        [dict(signature, signature_id="perspective-2"), dict(signature, signature_id="perspective-3")],
        max_records=2,
    )
    assert count == 2
    assert len(state["knowledge_graph"]["perspective_signatures"]) == 2

    assert record_perspective_signatures(state, [signature], max_records=0) == 0
    assert state["knowledge_graph"]["perspective_signatures"] == {}

    print("Stage 5.5B perspective-signature state audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit persistence of validity scopes without altering proposition identity."""

from core.validity_state import record_validity_scope, record_validity_scopes


def main() -> int:
    state = {"knowledge_graph": {"propositions": {"P1": {}}, "validity_scopes": {}}}
    first = {
        "validity_id": "V1",
        "proposition_id": "P1",
        "type": "conditional",
        "conditions": ["X"],
        "status": "proposed",
    }
    assert record_validity_scope(state, first)
    assert state["knowledge_graph"]["validity_scopes"]["V1"]["proposition_id"] == "P1"

    assessed = dict(first, status="assessed")
    assert record_validity_scope(state, assessed)
    assert state["knowledge_graph"]["validity_scopes"]["V1"]["status"] == "assessed"

    proposed_again = dict(first, status="proposed", conditions=["Y"])
    assert record_validity_scope(state, proposed_again)
    saved = state["knowledge_graph"]["validity_scopes"]["V1"]
    assert saved["status"] == "assessed"
    assert saved["conditions"] == ["Y"]

    count = record_validity_scopes(state, [first, dict(first, validity_id="V2")], max_records=1)
    assert count == 2
    assert len(state["knowledge_graph"]["validity_scopes"]) == 1

    state["knowledge_graph"]["validity_scopes"]["V2"] = first
    assert record_validity_scopes(state, [first], max_records=0) == 0
    assert state["knowledge_graph"]["validity_scopes"] == {}
    assert state["knowledge_graph"]["propositions"]["P1"] == {}

    print("Stage 4.5D validity-state audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

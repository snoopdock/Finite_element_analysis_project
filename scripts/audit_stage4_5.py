#!/usr/bin/env python3
"""Combined audit for the Stage 4.5 validity-scope hardening layer."""

from analysis.validity_scope import ValidityScope, normalize_validity_scope
from analysis.validity_context_mapping import propose_validity_scope
from analysis.validity_scope_conflicts import compare_validity_scopes
from core.validity_state import record_validity_scope


def main() -> int:
    proposition = {
        "proposition_id": "P1",
        "framework": "Galerkin FEM",
        "domain_of_validity": "elliptic PDE",
        "conditions": ["coercive operator"],
        "assumptions": ["bounded domain"],
        "evidence_relation_ids": ["ER1"],
    }

    scope = propose_validity_scope(proposition)
    assert scope is not None
    assert scope["status"] == "proposed"
    assert scope["type"] == "conditional"
    assert scope["evidence_relation_ids"] == ["ER1"]

    model = ValidityScope(**scope)
    assert normalize_validity_scope(model) == scope

    state = {"knowledge_graph": {"propositions": {"P1": proposition}}}
    assert record_validity_scope(state, scope)
    assert "V1" not in state["knowledge_graph"]["validity_scopes"]
    assert scope["validity_id"] in state["knowledge_graph"]["validity_scopes"]

    broader = dict(scope)
    broader["validity_id"] = "V2"
    broader["conditions"] = ["coercive operator", "bounded domain"]
    comparison = compare_validity_scopes(scope, broader)
    assert comparison["status"] == "compatible_or_overlapping"
    assert comparison["scientific_resolution"] == "not_performed"

    framework_change = dict(scope)
    framework_change["validity_id"] = "V3"
    framework_change["framework"] = "Finite Volume"
    comparison = compare_validity_scopes(scope, framework_change)
    assert comparison["status"] == "different_framework"

    # Validity scope itself must not become a truth/verification assertion.
    assert all(item["status"] == "proposed" for item in state["knowledge_graph"]["validity_scopes"].values())
    print("Stage 4.5 combined audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

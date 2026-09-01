#!/usr/bin/env python3
"""Audit coexistence of the hardened scientific object layers.

This is a structural audit. It does not require network access or an LLM.
"""

from analysis.assertion_provenance import AssertionRecord
from analysis.epistemic_state import normalize_epistemic_state
from analysis.perspective_signature import signature_from_propositions
from analysis.proposition_lifecycle import normalize_lifecycle_event
from analysis.relationship_support import normalize_relationship_support
from analysis.validity_scope import ValidityScope


def main() -> int:
    proposition = {
        "proposition_id": "p-001",
        "statement": "Method A converges under coercivity.",
        "framework": "Galerkin FEM",
        "assumptions": ["coercive operator"],
        "conditions": ["bounded domain"],
        "domain_of_validity": "elliptic PDE",
        "source_ids": ["s-001"],
    }

    scope = ValidityScope(
        validity_id="v-001",
        proposition_id="p-001",
        type="conditional",
        framework="Galerkin FEM",
        domain_of_validity="elliptic PDE",
        conditions=["bounded domain"],
        assumptions=["coercive operator"],
        status="proposed",
    ).to_dict()
    assert scope["proposition_id"] == proposition["proposition_id"]

    assertion = AssertionRecord(
        assertion_id="a-001",
        proposition_id="p-001",
        source_id="s-001",
        role="proposes",
        validity_id="v-001",
        evidence_relation_ids=["er-001"],
        passage_ids=["passage-001"],
        status="proposed",
    ).to_dict()
    assert assertion["validity_id"] == scope["validity_id"]
    assert assertion["proposition_id"] == proposition["proposition_id"]

    lifecycle = normalize_lifecycle_event({
        "event_id": "l-001",
        "proposition_id": "p-001",
        "change_type": "restriction",
        "related_proposition_ids": ["p-002"],
        "status": "proposed",
    })
    assert lifecycle is not None
    assert lifecycle["proposition_id"] == "p-001"
    assert lifecycle["related_proposition_ids"] == ["p-002"]

    epistemic = normalize_epistemic_state({
        "status": "conditional",
        "evidence_strength": "moderate",
        "literature_agreement": "mixed",
        "model_confidence": 0.82,
    })
    assert epistemic["status"] == "conditional"
    assert epistemic["model_confidence"] == 0.82

    signature = signature_from_propositions([proposition])
    assert signature is not None
    assert "p-001" in signature["proposition_ids"]
    assert "s-001" in signature["source_ids"]

    support = normalize_relationship_support({
        "support_id": "rs-001",
        "relationship_id": "r-001",
        "support_type": "supports",
        "proposition_ids": ["p-001"],
        "source_ids": ["s-001"],
        "status": "proposed",
    })
    assert support is not None
    assert support["proposition_ids"] == ["p-001"]

    # Composition invariant: none of these objects changes proposition identity.
    assert scope["proposition_id"] == assertion["proposition_id"] == lifecycle["proposition_id"]

    print("H1 scientific object composition audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

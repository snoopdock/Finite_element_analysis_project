#!/usr/bin/env python3
"""Audit structured perspective-signature creation."""

from analysis.perspective_signature import signature_from_propositions, signature_id_from_payload


def main() -> int:
    propositions = [
        {
            "proposition_id": "P1",
            "statement": "Method A is stable under coercivity.",
            "framework": "Galerkin FEM",
            "assumptions": ["bounded domain"],
            "method": "weak formulation",
            "domain_of_validity": "elliptic PDE",
            "limitations": ["nonlinear regime"],
            "source_ids": ["S1"],
        },
        {
            "proposition_id": "P2",
            "statement": "Method A is stable under coercivity.",
            "framework": "Galerkin FEM",
            "assumptions": ["coercivity"],
            "method": "weak formulation",
            "domain_of_validity": "elliptic PDE",
            "source_ids": ["S2"],
        },
    ]
    signature = signature_from_propositions(propositions)
    assert signature is not None
    assert signature["framework"] == "Galerkin FEM"
    assert "bounded domain" in signature["assumptions"]
    assert signature["proposition_ids"] == ["P1", "P2"]
    assert signature["source_ids"] == ["S1", "S2"]
    assert signature["signature_id"] == signature_from_propositions(propositions)["signature_id"]

    # Signature identity depends on structured perspective content, not list order.
    reversed_signature = signature_from_propositions(list(reversed(propositions)))
    assert reversed_signature is not None
    assert reversed_signature["signature_id"] == signature["signature_id"]

    payload = {"framework": "FEM", "claims": ["P"]}
    assert signature_id_from_payload(payload).startswith("perspective-")

    # Signatures describe perspectives; they do not establish scientific truth.
    assert "verified" not in signature
    assert "truth" not in signature

    print("Stage 5.5A perspective-signature audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

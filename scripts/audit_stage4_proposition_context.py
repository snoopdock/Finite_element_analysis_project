#!/usr/bin/env python3
"""Read-only audit for proposition scientific-context normalization.

Run from the repository root:
    python scripts/audit_stage4_proposition_context.py

Uses in-memory records only and never calls an LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.knowledge_graph import normalize_proposition


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        proposition = normalize_proposition({
            "statement": "A stable formulation exists.",
            "framework": "linear elasticity",
            "assumptions": ["small strain"],
            "conditions": ["quasi-static"],
            "domain_of_validity": ["small deformation"],
            "definitions": ["u is displacement"],
            "parameters": ["E", "nu"],
            "boundary_conditions": ["Dirichlet"],
            "initial_conditions": ["zero displacement"],
            "method": "Galerkin",
            "approximation": ["piecewise linear basis"],
            "scope": "one-dimensional test case",
            "source_ids": ["paper-a"],
        })

        context = proposition["context"]
        _assert(context["framework"] == "linear elasticity", "Framework not propagated.")
        _assert(context["assumptions"] == ["small strain"], "Assumptions not propagated.")
        _assert(context["boundary_conditions"] == ["Dirichlet"], "Boundary conditions not propagated.")
        _assert(context["scope"] == "one-dimensional test case", "Scope not propagated.")
        _assert(proposition["framework"] == context["framework"], "Legacy and context framework fields diverged.")
        _assert(proposition["assumptions"] == context["assumptions"], "Legacy and context assumptions diverged.")
        _assert(proposition["conditions"] == context["conditions"], "Legacy and context conditions diverged.")
        _assert(proposition["source_ids"] == ["paper-a"], "Source provenance changed.")

        print("Stage 4 proposition-context runtime audit")
        print("==========================================")
        print("PASS: context view, legacy fields, and provenance remain aligned.")
        return 0
    except Exception as exc:
        print(f"STAGE 4 PROPOSITION CONTEXT AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only Stage 4 scientific-context runtime audit.

Run from the repository root:
    python scripts/audit_stage4_context.py

Uses in-memory records only; it never calls an LLM or writes project state.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.scientific_context import context_difference, normalize_context


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        normalized = normalize_context({
            "framework": " small-deformation  elasticity ",
            "assumptions": ["small deformation", "small deformation", ""],
            "conditions": "quasi-static",
            "parameters": {"Re": 100, "": "ignored"},
            "scope_notes": "linear regime",
        })

        _assert(normalized["framework"] == "small-deformation elasticity", "Framework normalization failed.")
        _assert(normalized["assumptions"] == ["small deformation"], "Assumption deduplication failed.")
        _assert(normalized["conditions"] == ["quasi-static"], "String-to-list normalization failed.")
        _assert(normalized["parameters"] == {"Re": "100"}, "Parameter normalization failed.")
        _assert(normalized["scope"] == "", "Unknown scope was incorrectly inferred from scope_notes.")
        _assert(normalized["scope_notes"] == "", "Canonical scope note should remain empty when scope is absent.")

        other = normalize_context({"framework": "finite-strain elasticity", "assumptions": ["large deformation"]})
        differences = context_difference(normalized, other)
        _assert("framework" in differences, "Framework difference was not detected.")
        _assert("assumptions" in differences, "Assumption difference was not detected.")

        print("Stage 4 context runtime audit")
        print("==============================")
        print("PASS: normalization, de-duplication, non-invention, and context-difference checks passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 4 CONTEXT AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

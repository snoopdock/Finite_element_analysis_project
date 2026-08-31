#!/usr/bin/env python3
"""Read-only audit for bounded scientific-context enrichment."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.context_enrichment import enrich_extraction_context


class _Parser:
    def parse(self, text, model_name=None):
        return {
            "framework": "test framework",
            "assumptions": ["small perturbation"],
            "conditions": ["steady state"],
            "domain_of_validity": ["test regime"],
            "scope": "test scope",
        }


class _Provider:
    def __init__(self):
        self.calls = 0

    def budget_exhausted(self):
        return False

    def chat(self, *args, **kwargs):
        self.calls += 1
        return '{"framework":"test framework","assumptions":["small perturbation"]}', None


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "full.txt"
            path.write_text("Actual full text about the claimed formulation.", encoding="utf-8")
            provider = _Provider()
            extraction = {
                "rules": [{"rule": "The formulation is stable.", "source_ids": ["paper-1"]}],
                "equations": [],
                "procedures": [],
                "concepts": [],
            }
            enriched = enrich_extraction_context(
                extraction,
                {"paper-1": {"source_id": "paper-1", "full_text_path": str(path)}},
                provider,
                _Parser(),
                max_items=1,
            )
            context = enriched["rules"][0].get("context", {})
            _assert(context.get("framework") == "test framework", "Context was not attached.")
            _assert(provider.calls == 1, "Unexpected number of context calls.")

            provider2 = _Provider()
            abstract_only = {
                "rules": [{"rule": "This must not be enriched.", "source_ids": ["paper-2"]}],
                "equations": [], "procedures": [], "concepts": [],
            }
            result = enrich_extraction_context(
                abstract_only,
                {"paper-2": {"source_id": "paper-2", "excerpt": "Abstract only."}},
                provider2,
                _Parser(),
                max_items=1,
            )
            _assert("context" not in result["rules"][0], "Abstract-only evidence was used.")
            _assert(provider2.calls == 0, "Abstract-only item consumed an LLM call.")

        print("Stage 4 enrichment runtime audit")
        print("=================================")
        print("PASS: bounded enrichment and full-text-only enforcement passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 4 ENRICHMENT AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

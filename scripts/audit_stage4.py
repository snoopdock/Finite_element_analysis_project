#!/usr/bin/env python3
"""Read-only combined Stage 4 scientific-context audit.

Run from the repository root:
    python scripts/audit_stage4.py

Uses in-memory data except for isolated temporary full text and never writes
project state or calls an external service.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.context_enrichment import enrich_extraction_context
from analysis.scientific_context import context_difference, normalize_context
from core.knowledge_graph import normalize_proposition
from core.knowledge_graph_builder import sync_legacy_knowledge_base


class _Parser:
    def parse(self, text, model_name=None):
        return {
            "framework": "test framework",
            "assumptions": ["A1"],
            "conditions": ["C1"],
            "domain_of_validity": ["D1"],
            "parameters": {"p": "1"},
            "scope": "test scope",
        }


class _Provider:
    def __init__(self):
        self.calls = 0

    def budget_exhausted(self):
        return False

    def chat(self, *args, **kwargs):
        self.calls += 1
        return '{"framework":"test framework","assumptions":["A1"]}', None


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        base = normalize_context({"framework": "F", "assumptions": ["A", "A"], "scope": "S"})
        other = normalize_context({"framework": "G", "assumptions": ["B"]})
        differences = context_difference(base, other)
        _assert("framework" in differences and "assumptions" in differences, "Context differences were not detected.")

        proposition = normalize_proposition({
            "statement": "P",
            "framework": "F",
            "assumptions": ["A"],
            "source_ids": ["paper-a"],
        })
        _assert(proposition["context"]["framework"] == "F", "Proposition context was not normalized.")
        _assert(proposition["context"]["assumptions"] == ["A"], "Proposition assumptions were not preserved.")

        state = {
            "knowledge_base": {
                "rules": [{
                    "rule": "R",
                    "source_ids": ["paper-a"],
                    "framework": "F",
                    "conditions": ["C"],
                }],
            },
            "knowledge_graph": {"concepts": {}, "propositions": {}, "relationships": {}, "concept_history": []},
        }
        sync_legacy_knowledge_base(state)
        bridged = next(iter(state["knowledge_graph"]["propositions"].values()))
        _assert(bridged["context"]["framework"] == "F", "Bridge lost framework.")
        _assert(bridged["context"]["conditions"] == ["C"], "Bridge lost conditions.")

        with tempfile.TemporaryDirectory() as tmp:
            text_path = Path(tmp) / "full.txt"
            text_path.write_text("full article text", encoding="utf-8")
            provider = _Provider()
            extraction = {"rules": [{"rule": "R2", "source_ids": ["paper-b"]}], "equations": [], "procedures": [], "concepts": []}
            enriched = enrich_extraction_context(
                extraction,
                {"paper-b": {"full_text_path": str(text_path)}},
                provider,
                _Parser(),
                max_items=1,
            )
            _assert("context" in enriched["rules"][0], "Context enrichment did not attach context.")
            _assert(provider.calls == 1, "Unexpected enrichment call count.")

        print("Stage 4 combined runtime audit")
        print("===============================")
        print("PASS: normalization, proposition context, legacy bridge, and full-text enrichment passed.")
        return 0
    except Exception as exc:
        print(f"STAGE 4 AUDIT: ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

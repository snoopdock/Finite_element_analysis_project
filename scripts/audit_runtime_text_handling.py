#!/usr/bin/env python3
"""Regression audit for LaTeX parsing and citation extraction.

This audit is deterministic and performs no network or LLM calls.
"""

from __future__ import annotations

from analysis.citation_validator import extract_citation_ids
from processing.llm_parser import UniversalLLMJSONParser


def main() -> int:
    parser = UniversalLLMJSONParser(verbose=False)

    # Strict JSON with correctly escaped LaTeX must preserve the TeX command.
    strict = parser.parse('{"latex": "\\\\partial u / \\partial x"}')
    assert strict["latex"] == "\\partial u / \\partial x"

    # Common single-quoted LLM output with unescaped LaTeX must normalize
    # without falling through to ast.literal_eval.
    single_quoted = parser.parse("{'latex': '\\partial u + \\theta = 0'}")
    assert single_quoted["latex"] == "\\partial u + \\theta = 0"

    known = {"SRC_001", "1009.0997v3"}
    citations = extract_citation_ids(
        r"Interval [0,1], variables [x,y], and sources [SRC_001, 1009.0997v3].",
        known_ids=known,
    )
    assert citations == ["1009.0997v3", "SRC_001"]

    # Unknown citation-like IDs remain detectable so genuine bad citations
    # are still reported rather than silently discarded.
    invalid = extract_citation_ids("Supported source [SRC_001] and bad source [BAD_REF].", known_ids=known)
    assert invalid == ["BAD_REF", "SRC_001"]

    print("Runtime text-handling audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

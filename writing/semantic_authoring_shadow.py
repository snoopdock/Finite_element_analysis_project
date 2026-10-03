#!/usr/bin/env python3
"""Deterministic semantic annotation of final legacy authoring text.

This migration-only boundary never rewrites scientific prose.  It replaces
only exact, authorized representations that can be deterministically projected
back to the original legacy text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Mapping, Set

from core.domain_semantic_model import (
    get_authorized_equation_ids,
    resolve_equation,
)


_TOKEN_RE = re.compile(
    r"\$(?P<math>.*?)\$|(?<!\[)\[(?P<cite>[^\[\]]+)\](?!\])",
    flags=re.DOTALL,
)
_MARKER_RE = re.compile(r"\[\[(?P<kind>EQ|CITE):(?P<identifier>[^\]]+)\]\]")


@dataclass(frozen=True)
class SemanticShadowResult:
    authoring_text: str
    annotated_equation_ids: tuple[str, ...] = field(default_factory=tuple)
    annotated_source_ids: tuple[str, ...] = field(default_factory=tuple)
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_semantic_markers(self) -> bool:
        return bool(self.annotated_equation_ids or self.annotated_source_ids)


def _is_standalone_math(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end].strip() == text[start:end].strip()


def _expression_index(domain_model: Mapping[str, Any]) -> Dict[str, list[str]]:
    index: Dict[str, list[str]] = {}
    for equation_id in sorted(get_authorized_equation_ids(domain_model)):
        equation = resolve_equation(domain_model, equation_id)
        expression = str(equation.get("expression", ""))
        if expression:
            index.setdefault(expression, []).append(equation_id)
    return index


def annotate_legacy_authoring(
    content: str,
    *,
    domain_model: Mapping[str, Any],
    source_ids: Set[str],
) -> SemanticShadowResult:
    """Annotate exact authorized equations/citations without changing prose."""
    if not isinstance(content, str):
        content = str(content)
    if "[[" in content:
        return SemanticShadowResult(
            authoring_text=content,
            diagnostics=("existing_semantic_marker_syntax",),
        )

    expression_index = _expression_index(domain_model)
    valid_sources = {str(source_id) for source_id in source_ids if source_id}
    diagnostics: list[str] = []
    annotated_equations: list[str] = []
    annotated_sources: list[str] = []
    pieces: list[str] = []
    cursor = 0

    for match in _TOKEN_RE.finditer(content):
        pieces.append(content[cursor:match.start()])
        replacement = match.group(0)

        if match.group("math") is not None:
            expression = match.group("math")
            matches = expression_index.get(expression, [])
            if not _is_standalone_math(content, match.start(), match.end()):
                if matches:
                    diagnostics.append(f"inline_equation_not_annotated:{expression}")
            elif len(matches) == 1:
                equation_id = matches[0]
                replacement = f"[[EQ:{equation_id}]]"
                annotated_equations.append(equation_id)
            elif len(matches) > 1:
                diagnostics.append(f"ambiguous_equation_expression:{expression}")
            elif expression:
                diagnostics.append(f"unauthorized_equation_expression:{expression}")

        else:
            raw_citation = str(match.group("cite") or "").strip()
            # Grouped citations are left untouched in Package 1 because the
            # current marker model has occurrence semantics for one source.
            if "," in raw_citation:
                diagnostics.append(f"grouped_citation_not_annotated:{raw_citation}")
            elif raw_citation in valid_sources:
                replacement = f"[[CITE:{raw_citation}]]"
                annotated_sources.append(raw_citation)

        pieces.append(replacement)
        cursor = match.end()

    pieces.append(content[cursor:])
    authoring_text = "".join(pieces)

    projected = project_shadow_to_legacy(
        authoring_text,
        domain_model=domain_model,
    )
    if projected != content:
        return SemanticShadowResult(
            authoring_text=content,
            diagnostics=tuple(diagnostics + ["round_trip_mismatch"]),
        )

    return SemanticShadowResult(
        authoring_text=authoring_text,
        annotated_equation_ids=tuple(annotated_equations),
        annotated_source_ids=tuple(annotated_sources),
        diagnostics=tuple(diagnostics),
    )


def project_shadow_to_legacy(
    authoring_text: str,
    *,
    domain_model: Mapping[str, Any],
) -> str:
    """Project Package-1 EQ/CITE markers back to legacy spelling."""
    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        identifier = match.group("identifier").strip()
        if kind == "CITE":
            return f"[{identifier}]"
        equation = resolve_equation(domain_model, identifier)
        return f"${equation['expression']}$"

    return _MARKER_RE.sub(replace, str(authoring_text))

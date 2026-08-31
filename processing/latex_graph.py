#!/usr/bin/env python3
"""Pure LaTeX/TikZ projection of the provenance-aware concept graph."""

from __future__ import annotations

import re
from typing import Dict, List


def _escape(text: object) -> str:
    value = str(text or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _short_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value))[:8] or "node"


def render_concept_graph(graph: Dict, *, max_nodes: int = 40) -> str:
    """Render a bounded concept/relationship graph as a TikZ picture."""
    graph = graph if isinstance(graph, dict) else {}
    concepts = graph.get("concepts", {})
    relationships = graph.get("relationships", {})

    if not isinstance(concepts, dict):
        concepts = {}
    if not isinstance(relationships, dict):
        relationships = {}

    ids = list(concepts)[: max(0, int(max_nodes))]
    allowed = set(ids)

    lines = [
        r"\begin{center}",
        r"\begin{tikzpicture}[", 
        r"  node distance=8mm and 12mm,",
        r"  concept/.style={draw, rounded corners, align=center, text width=3.4cm, font=\small},",
        r"  relation/.style={-Latex, font=\scriptsize}",
        r"]",
    ]

    for index, concept_id in enumerate(ids):
        concept = concepts.get(concept_id, {})
        title = _escape(concept.get("name", "Unnamed concept"))
        node_id = _short_id(concept_id)
        if index == 0:
            lines.append(f"  \\node[concept] ({node_id}) {{{title}}};")
        else:
            lines.append(
                f"  \\node[concept, below=of {_short_id(ids[index - 1])}] ({node_id}) {{{title}}};"
            )

    for relationship in relationships.values():
        if not isinstance(relationship, dict):
            continue
        source = relationship.get("source_id")
        target = relationship.get("target_id")
        if source not in allowed or target not in allowed:
            continue
        label = _escape(relationship.get("type", "related_to"))
        lines.append(
            f"  \\draw[relation] ({_short_id(source)}) -- node[above] {{{label}}} ({_short_id(target)});"
        )

    lines.extend([
        r"\end{tikzpicture}",
        r"\end{center}",
    ])
    return "\n".join(lines)

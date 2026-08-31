#!/usr/bin/env python3
"""Pure LaTeX/TikZ projection of the provenance-aware concept graph."""

from __future__ import annotations

from typing import Dict


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


def render_concept_graph(graph: Dict, *, max_nodes: int = 40) -> str:
    """Render a bounded concept graph with collision-safe node identifiers."""
    graph = graph if isinstance(graph, dict) else {}
    concepts = graph.get("concepts", {})
    relationships = graph.get("relationships", {})
    if not isinstance(concepts, dict):
        concepts = {}
    if not isinstance(relationships, dict):
        relationships = {}

    ids = list(concepts)[: max(0, int(max_nodes))]
    node_names = {concept_id: f"conceptnode{index}" for index, concept_id in enumerate(ids)}

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
        node_id = node_names[concept_id]
        if index == 0:
            lines.append(f"  \\node[concept] ({node_id}) {{{title}}};")
        else:
            previous_id = node_names[ids[index - 1]]
            lines.append(
                f"  \\node[concept, below=of {previous_id}] ({node_id}) {{{title}}};"
            )

    for relationship in relationships.values():
        if not isinstance(relationship, dict):
            continue
        source = relationship.get("source_id")
        target = relationship.get("target_id")
        if source not in node_names or target not in node_names:
            continue
        label = _escape(relationship.get("type", "related_to"))
        lines.append(
            f"  \\draw[relation] ({node_names[source]}) -- node[above] {{{label}}} ({node_names[target]});"
        )

    lines.extend([
        r"\end{tikzpicture}",
        r"\end{center}",
    ])
    return "\n".join(lines)


def render_perspective_table(graph: Dict, *, max_rows: int = 30) -> str:
    """Render proposition relationships as a compact LaTeX table."""
    graph = graph if isinstance(graph, dict) else {}
    propositions = graph.get("propositions", {})
    relationships = graph.get("relationships", {})
    if not isinstance(propositions, dict) or not isinstance(relationships, dict):
        return "No perspective relationships recorded."

    rows = []
    for relationship in relationships.values():
        if not isinstance(relationship, dict):
            continue
        source = propositions.get(relationship.get("source_id"))
        target = propositions.get(relationship.get("target_id"))
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        source_text = _escape(str(source.get("statement", ""))[:180])
        target_text = _escape(str(target.get("statement", ""))[:180])
        relation = _escape(relationship.get("type", "related_to"))
        rows.append(
            f"{source_text} & {relation} & {target_text} \\\\"
        )
        if len(rows) >= max(0, int(max_rows)):
            break

    if not rows:
        return "No perspective relationships recorded."

    return "\n".join([
        r"\begin{longtable}{@{}p{0.37\textwidth}p{0.16\textwidth}p{0.37\textwidth}@{}}",
        r"\toprule",
        r"\textbf{Proposition A} & \textbf{Relationship} & \textbf{Proposition B} \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"\textbf{Proposition A} & \textbf{Relationship} & \textbf{Proposition B} \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
        *rows,
        r"\end{longtable}",
    ])

#!/usr/bin/env python3
"""LaTeX/TikZ projection for explicit graph publication IR blocks.

This module never reads runtime knowledge-graph state. It renders only the
bounded semantic publication view already selected upstream and uses the same
plain-text escaping policy as the rest of the renderer.
"""

from __future__ import annotations

from processing.latex_ir import ConceptGraphBlock, RelationshipTableBlock
from utils.latex import escape_text


def _selection_note(selected: int, total: int, policy: str, noun: str) -> str:
    if selected >= total:
        return ""
    return (
        r"\par\small\textit{Publication view: showing "
        + str(selected)
        + " of "
        + str(total)
        + " "
        + escape_text(noun)
        + "; selection policy: "
        + escape_text(policy.replace("_", " "))
        + r".}"
    )


def render_concept_graph(block: ConceptGraphBlock) -> str:
    """Render one explicit ConceptGraphBlock without applying selection policy."""
    node_names = {
        node.concept_id: f"conceptnode{index}" for index, node in enumerate(block.nodes)
    }
    lines = [
        r"\begin{center}",
        r"\begin{tikzpicture}[",
        r"  concept/.style={draw, rounded corners, align=center, text width=3.6cm, font=\small},",
        r"  relation/.style={-Latex, font=\scriptsize}",
        r"]",
    ]

    # A bounded three-column grid avoids the pathological vertical stack used
    # by the legacy renderer. Selection size is decided upstream.
    columns = 3
    x_spacing = 5.0
    y_spacing = 2.2
    for index, node in enumerate(block.nodes):
        row = index // columns
        column = index % columns
        x = column * x_spacing
        y = -row * y_spacing
        title = escape_text(node.name)
        lines.append(
            f"  \\node[concept] ({node_names[node.concept_id]}) at ({x:.1f},{y:.1f}) {{{title}}};"
        )

    for relation in block.relations:
        label = escape_text(relation.relation_type.replace("_", " "))
        lines.append(
            "  \\draw[relation] "
            f"({node_names[relation.source_concept_id]}) -- "
            f"node[above] {{{label}}} "
            f"({node_names[relation.target_concept_id]});"
        )

    lines.extend([r"\end{tikzpicture}", r"\end{center}"])

    if not block.relations:
        lines.append(
            r"\par\small\textit{No concept-to-concept relationships are recorded "
            r"inside this publication view.}"
        )

    node_note = _selection_note(
        len(block.nodes), block.total_concepts, block.selection_policy, "concepts"
    )
    if node_note:
        lines.append(node_note)

    if len(block.relations) < block.total_concept_relations:
        lines.append(
            r"\par\small\textit{Only relationships whose endpoints are present in "
            r"the selected concept view are rendered; authoritative graph identity "
            r"is retained outside the publication view.}"
        )

    return "\n".join(lines)


def render_relationship_table(block: RelationshipTableBlock) -> str:
    """Render one explicit proposition-relationship publication view."""
    rows = [
        " & ".join(
            [
                escape_text(row.source_statement),
                escape_text(row.relation_type.replace("_", " ")),
                escape_text(row.target_statement),
            ]
        )
        + r" \\"
        for row in block.rows
    ]

    lines = [
        r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{0.37\textwidth}"
        r">{\raggedright\arraybackslash}p{0.16\textwidth}"
        r">{\raggedright\arraybackslash}p{0.37\textwidth}@{}}",
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
    ]

    note = _selection_note(
        len(block.rows),
        block.total_relationships,
        block.selection_policy,
        "relationships",
    )
    if note:
        lines.append(note)
    return "\n".join(lines)

from processing.latex_capabilities import render_package_lines
from processing.latex_ir import (
    ConceptGraphBlock,
    ConceptGraphNodeIR,
    DocumentModel,
    FigureBlock,
    IRMathSpan,
    IRTextSpan,
    ParagraphBlock,
    SectionModel,
    TableBlock,
)


def _document(*blocks):
    return DocumentModel(
        topic="FEM",
        objective="Guide",
        sections=(
            SectionModel(
                title="S",
                section_id="11111111-1111-4111-8111-111111111111",
                label="sec:11111111-1111-4111-8111-111111111111",
                blocks=tuple(blocks),
            ),
        ),
        references=(),
    )


def test_preamble_is_feature_driven_for_plain_text():
    lines = render_package_lines(_document(ParagraphBlock((IRTextSpan("Body"),))))
    joined = "\n".join(lines)
    assert r"\usepackage{graphicx}" not in joined
    assert r"\usepackage{float}" not in joined
    assert r"\usepackage{tabularx}" not in joined
    assert r"\usepackage{tikz}" not in joined
    assert r"\usepackage{amsmath" not in joined
    assert r"\usepackage{enumitem}" not in joined
    assert joined.rindex(r"\usepackage{hyperref}") > joined.rindex(r"\usepackage{array}")


def test_preamble_enables_math_graph_figure_and_table_capabilities_only_when_present():
    graph = ConceptGraphBlock(
        occurrence_id="graph-view",
        nodes=(ConceptGraphNodeIR("c1", "Concept", "concept"),),
        relations=(),
        total_concepts=1,
        total_concept_relations=0,
        selection_policy="all",
    )
    lines = render_package_lines(
        _document(
            ParagraphBlock((IRMathSpan(r"u \in V"),)),
            graph,
            FigureBlock("fig-1", "figures/a.png", "Caption", "fig:fig-1"),
            TableBlock("tab-1", ("A",), (("B",),), "Caption", "tab:tab-1"),
        )
    )
    joined = "\n".join(lines)
    assert r"\usepackage{amsmath, amssymb}" in joined
    assert r"\usepackage{graphicx}" in joined
    assert r"\usepackage{float}" in joined
    assert r"\usepackage{tabularx}" in joined
    assert r"\usepackage{tikz}" in joined
    assert r"\usetikzlibrary{arrows.meta}" in joined

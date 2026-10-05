from pathlib import Path

import pytest

from core.document_model import (
    CrossReferenceOccurrence,
    Document,
    DocumentModelError,
    Figure,
    Paragraph,
    Section,
    Table,
    Text,
)
from core.domain_semantic_model import empty_domain_semantic_model
from processing.document_to_latex_ir import (
    DocumentToLatexIRError,
    project_document_to_latex_ir,
)
from processing.latex_ir import (
    DocumentModel,
    DocumentModelError as IRDocumentModelError,
    FigureBlock,
    IRCrossReferenceSpan,
    ParagraphBlock,
    SectionModel,
    TableBlock,
    normalize_sections,
    validate_document_model,
)
from processing.latex_renderer import render_body
from processing.latex_ir import citation_key_for_source_id


SECTION_ID = "11111111-1111-4111-8111-111111111111"


def _state():
    return {"topic": "FEM", "objective": "Guide"}


def _evidence():
    return [
        {
            "source_id": "source-1",
            "title": "Source One",
            "url": "https://example.com/source-1",
            "retriever_module": "research.test",
            "retrieved_at": "2026-10-05T00:00:00+00:00",
        }
    ]


def test_semantic_figure_and_table_validate_and_serialize_strict_payloads():
    figure = Figure(
        asset="assets/mesh.png",
        figure_id="figure-mesh",
        caption="Finite element mesh",
        source_ids=["source-1"],
    )
    table = Table(
        columns=["Element", "Error"],
        rows=[["E1", "0.10"], ["E2", "0.05"]],
        table_id="table-errors",
        caption="Element error indicators",
        source_ids=["source-1"],
    )

    figure.validate()
    table.validate()
    assert figure.to_dict()["figure_id"] == "figure-mesh"
    assert table.to_dict()["rows"][1] == ["E2", "0.05"]


def test_semantic_table_rejects_shape_mismatch_and_non_string_cells():
    with pytest.raises(DocumentModelError, match="expected 2"):
        Table(columns=["A", "B"], rows=[["only-one"]]).validate()

    with pytest.raises(DocumentModelError, match="cells must all be strings"):
        Table(columns=["A"], rows=[[3]]).validate()


def test_semantic_figure_and_table_reject_duplicate_or_empty_source_ids():
    with pytest.raises(DocumentModelError, match="must not contain duplicates"):
        Figure(asset="mesh.png", source_ids=["source-1", "source-1"]).validate()

    with pytest.raises(DocumentModelError, match="non-empty strings"):
        Table(columns=["A"], rows=[["x"]], source_ids=[""]).validate()


def test_projection_preserves_figure_table_order_and_generates_labels():
    document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Objects",
                children=[
                    Paragraph.from_text("Before."),
                    Figure(
                        asset="assets/mesh.png",
                        figure_id="figure-mesh",
                        caption="Finite element mesh",
                        source_ids=["source-1"],
                    ),
                    Table(
                        columns=["Element", "Error"],
                        rows=[["E1", "0.10"]],
                        table_id="table-errors",
                        caption="Element error indicators",
                        source_ids=["source-1"],
                    ),
                    Paragraph.from_text("After."),
                ],
            )
        ]
    )

    projected = project_document_to_latex_ir(
        document,
        state=_state(),
        evidence=_evidence(),
        domain_model=empty_domain_semantic_model(),
    )

    blocks = projected.sections[0].blocks
    assert [type(block).__name__ for block in blocks] == [
        "ParagraphBlock",
        "FigureBlock",
        "TableBlock",
        "ParagraphBlock",
    ]
    assert blocks[1].label == "fig:figure-mesh"
    assert blocks[2].label == "tab:table-errors"


def test_projection_rejects_manual_figure_and_table_labels():
    figure_document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Figure",
                children=[
                    Figure(
                        asset="mesh.png",
                        figure_id="figure-1",
                        caption="Mesh",
                        label="fig:manual",
                    )
                ],
            )
        ]
    )
    with pytest.raises(DocumentToLatexIRError, match="figure labels"):
        project_document_to_latex_ir(
            figure_document,
            state=_state(),
            evidence=[],
            domain_model=empty_domain_semantic_model(),
        )

    table_document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Table",
                children=[
                    Table(
                        columns=["A"],
                        rows=[["x"]],
                        table_id="table-1",
                        caption="Values",
                        label="tab:manual",
                    )
                ],
            )
        ]
    )
    with pytest.raises(DocumentToLatexIRError, match="table labels"):
        project_document_to_latex_ir(
            table_document,
            state=_state(),
            evidence=[],
            domain_model=empty_domain_semantic_model(),
        )


def test_projection_requires_caption_for_numbered_figure_and_table():
    figure_document = Document(
        children=[Section(section_id=SECTION_ID, title="Figure", children=[Figure(asset="mesh.png", figure_id="figure-1")])]
    )
    with pytest.raises(DocumentToLatexIRError, match="requires a non-empty caption"):
        project_document_to_latex_ir(
            figure_document, state=_state(), evidence=[], domain_model=empty_domain_semantic_model()
        )

    table_document = Document(
        children=[Section(section_id=SECTION_ID, title="Table", children=[Table(columns=["A"], rows=[["x"]], table_id="table-1")])]
    )
    with pytest.raises(DocumentToLatexIRError, match="requires a non-empty caption"):
        project_document_to_latex_ir(
            table_document, state=_state(), evidence=[], domain_model=empty_domain_semantic_model()
        )


def test_projection_rejects_unsafe_figure_asset_paths():
    for asset in ("../secret.png", "/tmp/mesh.png", "https://example.com/mesh.png", "mesh image.png", "mesh.svg"):
        document = Document(
            children=[
                Section(
                    section_id=SECTION_ID,
                    title="Figure",
                    children=[Figure(asset=asset, figure_id="figure-1", caption="Mesh")],
                )
            ]
        )
        with pytest.raises(DocumentToLatexIRError, match="unsafe asset path"):
            project_document_to_latex_ir(
                document, state=_state(), evidence=[], domain_model=empty_domain_semantic_model()
            )


def test_ir_validator_rechecks_asset_policy_for_hand_built_ir():
    ir = DocumentModel(
        topic="FEM",
        objective="Guide",
        sections=(
            SectionModel(
                title="Bad figure",
                section_id=SECTION_ID,
                label=f"sec:{SECTION_ID}",
                blocks=(
                    FigureBlock(
                        figure_id="figure-1",
                        asset="../secret.png",
                        caption="Bad",
                        label="fig:figure-1",
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(IRDocumentModelError, match="asset is unsafe"):
        validate_document_model(ir)


def test_figure_and_table_cross_references_resolve_to_emitted_anchors():
    document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Objects",
                children=[
                    Figure(asset="mesh.png", figure_id="figure-1", caption="Mesh"),
                    Table(columns=["A"], rows=[["x"]], table_id="table-1", caption="Values"),
                    Paragraph(
                        inline_content=[
                            Text("See "),
                            CrossReferenceOccurrence("figure-1", occurrence_id="xref-fig"),
                            Text(" and "),
                            CrossReferenceOccurrence("table-1", occurrence_id="xref-tab"),
                            Text("."),
                        ]
                    ),
                ],
            )
        ]
    )

    projected = project_document_to_latex_ir(
        document, state=_state(), evidence=[], domain_model=empty_domain_semantic_model()
    )
    paragraph = projected.sections[0].blocks[-1]
    refs = [item for item in paragraph.content if isinstance(item, IRCrossReferenceSpan)]
    assert [(item.target_type, item.label) for item in refs] == [
        ("figure", "fig:figure-1"),
        ("table", "tab:table-1"),
    ]
    body = render_body(projected)
    assert r"\label{fig:figure-1}" in body
    assert r"\label{tab:table-1}" in body
    assert r"\ref{fig:figure-1}" in body
    assert r"\ref{tab:table-1}" in body


def test_renderer_escapes_figure_table_text_and_renders_provenance_citations():
    document = Document(
        children=[
            Section(
                section_id=SECTION_ID,
                title="Objects",
                children=[
                    Figure(
                        asset="mesh.png",
                        figure_id="figure-1",
                        caption="Mesh & convergence_1",
                        source_ids=["source-1"],
                    ),
                    Table(
                        columns=["Name", "Value_%"],
                        rows=[["mesh_A", "50%"]],
                        table_id="table-1",
                        caption="Results & checks",
                        source_ids=["source-1"],
                    ),
                ],
            )
        ]
    )
    projected = project_document_to_latex_ir(
        document, state=_state(), evidence=_evidence(), domain_model=empty_domain_semantic_model()
    )
    body = render_body(projected)

    assert r"\begin{figure}[H]" in body
    assert r"\caption{Mesh \& convergence\_1}" in body
    assert r"\begin{table}[H]" in body
    assert r"\textbf{Value\_\%}" in body
    assert r"mesh\_A & 50\%" in body
    key = citation_key_for_source_id("source-1")
    assert body.count(rf"\cite{{{key}}}") == 2


def test_normalize_sections_supports_closed_figure_table_ir_language():
    sections = normalize_sections(
        [
            {
                "title": "Objects",
                "section_id": SECTION_ID,
                "label": f"sec:{SECTION_ID}",
                "blocks": [
                    {
                        "type": "figure",
                        "figure_id": "figure-1",
                        "asset": "mesh.png",
                        "caption": "Mesh",
                        "label": "fig:figure-1",
                        "source_ids": [],
                    },
                    {
                        "type": "table",
                        "table_id": "table-1",
                        "columns": ["A"],
                        "rows": [["x"]],
                        "caption": "Values",
                        "label": "tab:table-1",
                        "source_ids": [],
                    },
                ],
            }
        ]
    )
    assert isinstance(sections[0].blocks[0], FigureBlock)
    assert isinstance(sections[0].blocks[1], TableBlock)

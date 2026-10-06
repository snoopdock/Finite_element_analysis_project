import uuid

from core.document_model import (
    ConceptGraphView,
    Document,
    Paragraph,
    RelationshipTableView,
    Section,
    Text,
)
from core.domain_semantic_model import empty_domain_semantic_model
from core.publication_semantics import (
    MAX_CONCEPT_GRAPH_NODES,
    build_publication_graph_sections,
)
from core.semantic_document_pipeline import build_semantic_render_document
from processing.document_to_latex_ir import project_document_to_latex_ir
from processing.latex_builder import build_latex_document_from_model
from processing.latex_ir import (
    ConceptGraphBlock,
    DocumentModel,
    ParagraphBlock,
    IRTextSpan,
    RelationshipTableBlock,
    SectionModel,
)
from processing.latex_renderer import render_body


def _uuid(index: int) -> str:
    return str(uuid.UUID(int=index + 1))


def test_publication_graph_selection_is_explicit_and_preserves_authoritative_uuids():
    concepts = {
        _uuid(i): {"concept_id": _uuid(i), "name": f"Concept {i}", "type": "concept"}
        for i in range(MAX_CONCEPT_GRAPH_NODES + 2)
    }
    relation_id = _uuid(100)
    graph = {
        "concepts": concepts,
        "propositions": {},
        "relationships": {
            relation_id: {
                "relationship_id": relation_id,
                "source_id": _uuid(0),
                "target_id": _uuid(1),
                "type": "depends_on",
            }
        },
    }

    views = build_publication_graph_sections(
        graph,
        document_id="11111111-1111-4111-8111-111111111111",
    )
    child = views.conceptual_map.children[0]
    assert isinstance(child, ConceptGraphView)
    assert len(child.nodes) == MAX_CONCEPT_GRAPH_NODES
    assert child.total_concepts == MAX_CONCEPT_GRAPH_NODES + 2
    assert child.selection_policy == "stable_graph_insertion_order_prefix"
    assert child.nodes[0].concept_id == _uuid(0)
    assert child.relations[0].relationship_id == relation_id
    # Publication view identity is distinct from authoritative graph identity.
    assert child.occurrence_id not in concepts


def test_semantic_render_document_contains_explicit_graph_publication_section():
    concept_id = _uuid(1)
    state = {
        "topic": "FEM",
        "objective": "Guide",
        "sections": [],
        "domain_semantic_model": empty_domain_semantic_model(),
        "knowledge_graph": {
            "concepts": {
                concept_id: {"concept_id": concept_id, "name": "Galerkin & FEM", "type": "method"}
            },
            "propositions": {},
            "relationships": {},
        },
    }
    document, report = build_semantic_render_document(state, evidence=[])
    assert len(document.children) == 1
    section = document.children[0]
    assert section.generated_from == "knowledge_graph"
    assert section.title == "Conceptual Map"
    assert isinstance(section.children[0], ConceptGraphView)
    assert report["publication_views"]["concept_graph"]["selected_concepts"] == 1


def test_graph_view_projects_to_ir_and_uses_central_text_escaping():
    concept_id = _uuid(1)
    document = Document(
        document_id="11111111-1111-4111-8111-111111111111",
        children=[
            Section(
                section_id="22222222-2222-4222-8222-222222222222",
                title="Conceptual Map",
                children=[
                    ConceptGraphView(
                        occurrence_id="33333333-3333-4333-8333-333333333333",
                        nodes=[],
                        relations=[],
                        total_concepts=0,
                        total_concept_relations=0,
                    )
                ],
            )
        ],
    )
    # Empty graph views are invalid by contract.
    try:
        document.validate()
    except Exception:
        pass
    else:
        raise AssertionError("empty ConceptGraphView should fail closed")

    views = build_publication_graph_sections(
        {
            "concepts": {
                concept_id: {"concept_id": concept_id, "name": "A&B_%", "type": "concept"}
            },
            "propositions": {},
            "relationships": {},
        },
        document_id="11111111-1111-4111-8111-111111111111",
    )
    document = Document(children=[views.conceptual_map])
    ir = project_document_to_latex_ir(
        document,
        state={"topic": "FEM", "objective": "Guide"},
        evidence=[],
        domain_model=empty_domain_semantic_model(),
    )
    assert isinstance(ir.sections[0].blocks[0], ConceptGraphBlock)
    rendered = render_body(ir)
    assert r"A\&B\_\%" in rendered
    assert r"\begin{tikzpicture}" in rendered


def test_relationship_table_is_semantic_snapshot_and_does_not_truncate_statements():
    source_id, target_id, relationship_id = _uuid(1), _uuid(2), _uuid(3)
    suffix = "END-OF-FULL-STATEMENT"
    long_statement = ("long proposition " * 30) + suffix
    views = build_publication_graph_sections(
        {
            "concepts": {},
            "propositions": {
                source_id: {"proposition_id": source_id, "statement": long_statement},
                target_id: {"proposition_id": target_id, "statement": "Target proposition"},
            },
            "relationships": {
                relationship_id: {
                    "relationship_id": relationship_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "type": "contrasts_with",
                }
            },
        },
        document_id="11111111-1111-4111-8111-111111111111",
    )
    child = views.relationship_table.children[0]
    assert isinstance(child, RelationshipTableView)
    assert child.rows[0].source_statement.endswith(suffix)

    ir = project_document_to_latex_ir(
        Document(children=[views.relationship_table]),
        state={"topic": "FEM", "objective": "Guide"},
        evidence=[],
        domain_model=empty_domain_semantic_model(),
    )
    assert isinstance(ir.sections[0].blocks[0], RelationshipTableBlock)
    assert suffix in render_body(ir)


def test_latex_builder_does_not_read_runtime_knowledge_graph_state():
    document = DocumentModel(
        topic="FEM",
        objective="Guide",
        sections=(
            SectionModel(
                title="Text",
                section_id="22222222-2222-4222-8222-222222222222",
                label="sec:22222222-2222-4222-8222-222222222222",
                blocks=(ParagraphBlock((IRTextSpan("Body"),)),),
            ),
        ),
        references=(),
    )
    tex_a = build_latex_document_from_model({"knowledge_graph": {"concepts": {"x": {}}}}, document)
    tex_b = build_latex_document_from_model({"knowledge_graph": {}}, document)
    assert tex_a == tex_b
    assert "Conceptual Map" not in tex_a
    assert "Information Type Classification" not in tex_a

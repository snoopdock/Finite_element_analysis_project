
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import SemanticContext
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def test_default_semantic_context_is_serialized(dependency_result):
    payload = dependency_result.to_dict()
    assert payload["semantic_context"]["graph_schema_version"] == "semantic_graph/v1"
    assert payload["semantic_context_fingerprint"].startswith("semantic-context:")


def test_semantic_context_fingerprint_is_deterministic():
    first = SemanticContext(projection_contract_version="ast-projection/v1")
    second = SemanticContext(projection_contract_version="ast-projection/v1")
    assert first.fingerprint == second.fingerprint


def test_semantic_context_change_changes_analysis_identity(verification_graph):
    query = GraphQuery("q", QueryType.DEPENDENCY, ["A"], {"max_depth": 2})
    first = SemanticGraphAnalysisService(
        verification_graph,
        semantic_context=SemanticContext(relationship_vocabulary_version="relations/v1"),
    ).analyze(query)
    second = SemanticGraphAnalysisService(
        verification_graph,
        semantic_context=SemanticContext(relationship_vocabulary_version="relations/v2"),
    ).analyze(query)
    assert first.graph_fingerprint == second.graph_fingerprint
    assert first.semantic_context.fingerprint != second.semantic_context.fingerprint
    assert first.analysis_id != second.analysis_id


def test_semantic_context_rejects_blank_required_version():
    try:
        SemanticContext(graph_schema_version="")
    except ValueError as exc:
        assert "graph_schema_version" in str(exc)
    else:
        raise AssertionError("blank graph schema version should fail")

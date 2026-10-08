from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import AuditWorkingMemory
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def test_service_routes_dependency_query(software_graph):
    memory = AuditWorkingMemory()
    service = SemanticGraphAnalysisService(software_graph, memory=memory)
    result = service.analyze(GraphQuery("q", QueryType.DEPENDENCY, ["app.py"]))

    assert result.analysis_type.value == "dependency"
    assert len(memory) == 1
    assert memory.get(result.analysis_id) == result


def test_analysis_identity_is_deterministic(software_graph):
    first = SemanticGraphAnalysisService(software_graph).analyze(
        GraphQuery("stable-query", QueryType.DEPENDENCY, ["app.py"])
    )
    second = SemanticGraphAnalysisService(software_graph).analyze(
        GraphQuery("stable-query", QueryType.DEPENDENCY, ["app.py"])
    )
    assert first.analysis_id == second.analysis_id


def test_working_memory_detects_stale_results(software_graph):
    service = SemanticGraphAnalysisService(software_graph)
    result = service.analyze(GraphQuery("q", QueryType.DEPENDENCY, ["app.py"]))

    software_graph.edges[0].metadata["line"] = 77
    new_result = SemanticGraphAnalysisService(software_graph).analyze(
        GraphQuery("q-new", QueryType.DEPENDENCY, ["app.py"])
    )

    assert result.graph_fingerprint != new_result.graph_fingerprint
    assert service.memory.get(
        result.analysis_id,
        current_graph_fingerprint=new_result.graph_fingerprint,
    ) is None
    assert service.memory.stale_analysis_ids(new_result.graph_fingerprint) == (
        result.analysis_id,
    )

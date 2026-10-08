from audit_engine.semantic_audit.graph.analysis import AnalysisStatus, PathAnalyzer
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def test_path_analysis_returns_shortest_observed_path(software_graph):
    query = GraphQuery(
        "path-db",
        QueryType.PATH,
        ["app.py"],
        {
            "target_entity": "db.py",
            "relation_types": ["IMPORTS"],
            "max_depth": 4,
        },
    )
    result = PathAnalyzer(software_graph).analyze(query)
    assert result.status is AnalysisStatus.COMPLETED
    assert result.metadata["path_length"] == 2
    assert [obs.object_id for obs in result.observations] == ["service.py", "db.py"]


def test_path_analysis_reports_no_match(software_graph):
    query = GraphQuery(
        "path-isolated",
        QueryType.PATH,
        ["app.py"],
        {"target_entity": "isolated.py", "max_depth": 4},
    )
    result = PathAnalyzer(software_graph).analyze(query)
    assert result.status is AnalysisStatus.NO_MATCH
    assert result.observations == ()
    assert result.evidence == ()

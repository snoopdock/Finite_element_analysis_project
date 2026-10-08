from audit_engine.semantic_audit.graph.analysis import (
    AnalysisStatus,
    DependencyAnalyzer,
)
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def test_direct_dependency_analysis(software_graph):
    query = GraphQuery("dep-direct", QueryType.DEPENDENCY, ["app.py"])
    result = DependencyAnalyzer(software_graph).analyze(query)

    assert result.status is AnalysisStatus.COMPLETED
    assert result.discovered_entities == ("service.py",)
    assert result.parameters["relation_types"] == ["IMPORTS", "DEPENDS_ON"]
    assert result.evidence[0].verification_status.value == "observed"


def test_transitive_dependency_analysis(software_graph):
    query = GraphQuery(
        "dep-transitive",
        QueryType.DEPENDENCY,
        ["app.py"],
        {"max_depth": 2},
    )
    result = DependencyAnalyzer(software_graph).analyze(query)

    assert result.discovered_entities == ("service.py", "db.py")
    triples = {
        (obs.subject_id, obs.predicate, obs.object_id)
        for obs in result.observations
    }
    assert ("app.py", "IMPORTS", "service.py") in triples
    assert ("service.py", "IMPORTS", "db.py") in triples


def test_dependency_relation_scope_is_explicit(software_graph):
    query = GraphQuery(
        "dep-uses",
        QueryType.DEPENDENCY,
        ["app.py"],
        {"relation_types": ["USES"]},
    )
    result = DependencyAnalyzer(software_graph).analyze(query)
    assert result.discovered_entities == ("logging.info",)


def test_dependency_analysis_is_not_a_finding(software_graph):
    query = GraphQuery("dep", QueryType.DEPENDENCY, ["app.py"])
    payload = DependencyAnalyzer(software_graph).analyze(query).to_dict()
    forbidden = {"violation", "finding", "correct", "incorrect", "truth"}
    assert forbidden.isdisjoint(payload.keys())


def test_default_dependency_scope_does_not_silently_treat_uses_as_import_dependency(software_graph):
    query = GraphQuery("dep-default-scope", QueryType.DEPENDENCY, ["app.py"])
    result = DependencyAnalyzer(software_graph).analyze(query)
    assert "logging.info" not in result.discovered_entities

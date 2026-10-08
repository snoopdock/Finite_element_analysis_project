import pytest

from audit_engine.semantic_audit.graph.queries import (
    GraphQuery,
    GraphQueryValidationError,
    QueryType,
    validate_query,
)


def test_query_rejects_missing_source(software_graph):
    query = GraphQuery("q", QueryType.STRUCTURAL, [])
    with pytest.raises(GraphQueryValidationError):
        validate_query(query, software_graph)


def test_query_rejects_unknown_semantic_identity(software_graph):
    query = GraphQuery("q", QueryType.STRUCTURAL, ["missing.py"])
    with pytest.raises(GraphQueryValidationError):
        validate_query(query, software_graph)


def test_path_query_requires_target(software_graph):
    query = GraphQuery("q", QueryType.PATH, ["app.py"])
    with pytest.raises(GraphQueryValidationError):
        validate_query(query, software_graph)


def test_path_query_rejects_unknown_target(software_graph):
    query = GraphQuery(
        "q",
        QueryType.PATH,
        ["app.py"],
        {"target_entity": "missing.py"},
    )
    with pytest.raises(GraphQueryValidationError):
        validate_query(query, software_graph)

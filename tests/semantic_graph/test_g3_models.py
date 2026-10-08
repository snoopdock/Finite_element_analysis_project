import pytest

from audit_engine.semantic_audit.graph.analysis import (
    AnalysisType,
    TraversalDirection,
    VerificationStatus,
)
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def test_query_normalizes_sources_to_tuple():
    query = GraphQuery("q1", QueryType.DEPENDENCY, ["module_a"])
    assert query.query_id == "q1"
    assert query.source_entities == ("module_a",)


def test_query_rejects_empty_identity():
    with pytest.raises(ValueError):
        GraphQuery("", QueryType.DEPENDENCY, ["module_a"])


def test_query_type_can_be_constructed_from_value():
    query = GraphQuery("q2", "path", ["module_a"], {"target_entity": "module_b"})
    assert query.query_type is QueryType.PATH


def test_controlled_analysis_vocabularies():
    assert AnalysisType.DEPENDENCY.value == "dependency"
    assert TraversalDirection.OUTGOING.value == "outgoing"
    assert VerificationStatus.OBSERVED.value == "observed"

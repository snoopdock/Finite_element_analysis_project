from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.graph.analysis import AnalysisType


def test_query_model():
    q = GraphQuery('q1', QueryType.DEPENDENCY, ['module_a'])
    assert q.query_id == 'q1'


def test_analysis_type():
    assert AnalysisType.DEPENDENCY.value == 'dependency'

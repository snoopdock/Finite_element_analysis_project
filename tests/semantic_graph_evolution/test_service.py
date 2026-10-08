from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import SemanticGraphEvolutionService


def _copy_graph(graph):
    new = SemanticGraph()
    for node in graph.nodes:
        new.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    for edge in graph.edges:
        new.add_edge(SemanticEdge(edge.source_id, edge.target_id, edge.relation_type, dict(edge.attributes), dict(edge.metadata)))
    return new


def test_service_binds_after_snapshot_to_before(base_graph, base_context):
    after = _copy_graph(base_graph)
    after.add_edge(SemanticEdge('b', 'c', 'CALLS'))
    result = SemanticGraphEvolutionService().compare(
        before_graph=base_graph,
        after_graph=after,
        before_context=base_context,
    )
    assert result.after_snapshot.parent_snapshot_id == result.before_snapshot.snapshot_id


def test_service_returns_graph_and_topology_deltas(base_graph, base_context):
    after = _copy_graph(base_graph)
    after.add_edge(SemanticEdge('b', 'c', 'CALLS'))
    result = SemanticGraphEvolutionService().compare(
        before_graph=base_graph,
        after_graph=after,
        before_context=base_context,
    )
    assert len(result.graph_delta.added_edges) == 1
    assert result.topology_delta.edge_count_delta == 1


def test_service_serializes_complete_evolution_result(base_graph, base_context):
    result = SemanticGraphEvolutionService().compare(
        before_graph=base_graph,
        after_graph=_copy_graph(base_graph),
        before_context=base_context,
    )
    payload = result.to_dict()
    assert payload['schema_version'] == 'semantic_graph_evolution_result/v1'
    assert 'invalidation_report' in payload

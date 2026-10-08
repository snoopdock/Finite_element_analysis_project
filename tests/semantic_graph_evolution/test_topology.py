from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import GraphSnapshot, compare_topology, summarize_topology


def test_topology_summary_counts_parallel_edges_and_isolates(base_graph, base_context):
    base_graph.add_edge(SemanticEdge('a', 'b', 'CALLS'))
    snapshot = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    summary = summarize_topology(snapshot)
    assert summary.node_count == 3
    assert summary.edge_count == 2
    assert summary.isolated_node_ids == ('c',)
    assert summary.degree_map()['a'].out_degree == 2


def test_topology_summary_counts_weak_components(base_graph, base_context):
    summary = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    assert summary.weak_component_count == 2


def test_topology_summary_counts_self_loops(base_graph, base_context):
    base_graph.add_edge(SemanticEdge('c', 'c', 'REFERENCES'))
    summary = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    assert summary.self_loop_count == 1


def test_topology_summary_relation_counts(base_graph, base_context):
    base_graph.add_edge(SemanticEdge('b', 'c', 'CALLS'))
    base_graph.add_edge(SemanticEdge('a', 'c', 'CALLS'))
    summary = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    assert summary.relation_count_map() == {'CALLS': 2, 'DEPENDS_ON': 1}


def test_topology_delta_reports_degree_and_relation_changes(base_graph, base_context):
    before = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    base_graph.add_edge(SemanticEdge('b', 'c', 'CALLS'))
    after = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    delta = compare_topology(before, after)
    assert delta.edge_count_delta == 1
    assert [item.relation_type for item in delta.relation_count_changes] == ['CALLS']
    assert {item.node_id for item in delta.degree_changes} == {'b', 'c'}


def test_topology_delta_reports_isolation_transition(base_graph, base_context):
    before = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    base_graph.add_edge(SemanticEdge('b', 'c', 'CALLS'))
    after = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    delta = compare_topology(before, after)
    assert delta.no_longer_isolated == ('c',)


def test_topology_payload_declares_descriptive_boundary(base_graph, base_context):
    summary = summarize_topology(GraphSnapshot.capture(base_graph, semantic_context=base_context))
    assert summary.to_dict()['interpretation_boundary'] == 'descriptive_topology_only'

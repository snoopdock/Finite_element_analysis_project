from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import GraphSnapshot, compare_snapshots


def _copy_graph(graph):
    new = SemanticGraph()
    for node in graph.nodes:
        new.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    for edge in graph.edges:
        new.add_edge(SemanticEdge(edge.source_id, edge.target_id, edge.relation_type, dict(edge.attributes), dict(edge.metadata)))
    return new


def test_noop_delta_for_same_state(base_graph, base_context):
    first = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    second = GraphSnapshot.capture(_copy_graph(base_graph), semantic_context=base_context)
    delta = compare_snapshots(first, second)
    assert delta.is_noop


def test_delta_reports_added_and_removed_nodes(base_graph, base_context):
    before_graph = _copy_graph(base_graph)
    after_graph = SemanticGraph()
    after_graph.add_node(SemanticNode('a', 'Module', {'lifecycle': 'production'}))
    after_graph.add_node(SemanticNode('b', 'Module', {'lifecycle': 'stable'}))
    after_graph.add_node(SemanticNode('d', 'Module'))
    after_graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'code:1'}))
    delta = compare_snapshots(
        GraphSnapshot.capture(before_graph, semantic_context=base_context),
        GraphSnapshot.capture(after_graph, semantic_context=base_context),
    )
    assert [n.node_id for n in delta.added_nodes] == ['d']
    assert [n.node_id for n in delta.removed_nodes] == ['c']


def test_delta_reports_node_mutation(base_graph, base_context):
    after_graph = _copy_graph(base_graph)
    after_graph.get_node('b').attributes['lifecycle'] = 'experimental'
    delta = compare_snapshots(
        GraphSnapshot.capture(base_graph, semantic_context=base_context),
        GraphSnapshot.capture(after_graph, semantic_context=base_context),
    )
    assert len(delta.modified_nodes) == 1
    assert delta.modified_nodes[0].node_id == 'b'


def test_edge_metadata_change_is_remove_plus_add(base_graph, base_context):
    after_graph = _copy_graph(base_graph)
    after_graph.edges[0].metadata['source_id'] = 'code:2'
    delta = compare_snapshots(
        GraphSnapshot.capture(base_graph, semantic_context=base_context),
        GraphSnapshot.capture(after_graph, semantic_context=base_context),
    )
    assert len(delta.removed_edges) == 1
    assert len(delta.added_edges) == 1


def test_delta_reports_semantic_context_change(base_graph, base_context):
    changed = type(base_context)(
        graph_schema_version=base_context.graph_schema_version,
        relationship_vocabulary_version='repo-relations/v2',
        projection_contract_version=base_context.projection_contract_version,
        analysis_contract_version=base_context.analysis_contract_version,
    )
    delta = compare_snapshots(
        GraphSnapshot.capture(base_graph, semantic_context=base_context),
        GraphSnapshot.capture(base_graph, semantic_context=changed),
    )
    assert delta.semantic_context_delta.changed
    assert delta.semantic_context_delta.changed_fields[0][0] == 'relationship_vocabulary_version'


def test_delta_identity_is_deterministic(base_graph, base_context):
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after_graph = _copy_graph(base_graph)
    after_graph.add_edge(SemanticEdge('b', 'c', 'CALLS'))
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    assert compare_snapshots(before, after).delta_id == compare_snapshots(before, after).delta_id


def test_identical_parallel_edges_preserve_multiplicity(base_context):
    before_graph = SemanticGraph()
    before_graph.add_node(SemanticNode('a', 'Module'))
    before_graph.add_node(SemanticNode('b', 'Module'))
    edge = SemanticEdge('a', 'b', 'CALLS', metadata={'source_id': 'code:1'})
    before_graph.add_edge(edge)
    before_graph.add_edge(SemanticEdge('a', 'b', 'CALLS', metadata={'source_id': 'code:1'}))
    after_graph = SemanticGraph()
    after_graph.add_node(SemanticNode('a', 'Module'))
    after_graph.add_node(SemanticNode('b', 'Module'))
    after_graph.add_edge(SemanticEdge('a', 'b', 'CALLS', metadata={'source_id': 'code:1'}))
    before = GraphSnapshot.capture(before_graph, semantic_context=base_context)
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    delta = compare_snapshots(before, after)
    assert len(before.edges) == 2
    assert len({item.edge_id for item in before.edges}) == 2
    assert len(delta.removed_edges) == 1
    assert delta.fully_removed_edge_fingerprints == ()

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticNode
from audit_engine.semantic_audit.evolution import GraphSnapshot


def test_snapshot_identity_is_deterministic(base_graph, base_context):
    first = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    second = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    assert first.snapshot_id == second.snapshot_id
    assert first.to_dict() == second.to_dict()


def test_snapshot_identity_changes_with_semantic_context(base_graph, base_context):
    first = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    changed = type(base_context)(
        graph_schema_version=base_context.graph_schema_version,
        relationship_vocabulary_version='repo-relations/v2',
        projection_contract_version=base_context.projection_contract_version,
        analysis_contract_version=base_context.analysis_contract_version,
    )
    second = GraphSnapshot.capture(base_graph, semantic_context=changed)
    assert first.graph_fingerprint == second.graph_fingerprint
    assert first.snapshot_id != second.snapshot_id


def test_snapshot_is_not_changed_when_source_graph_mutates(base_graph, base_context):
    snapshot = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    base_graph.add_node(SemanticNode('d', 'Module'))
    base_graph.add_edge(SemanticEdge('b', 'd', 'CALLS'))
    assert [node.node_id for node in snapshot.nodes] == ['a', 'b', 'c']
    assert len(snapshot.edges) == 1


def test_snapshot_nested_metadata_is_frozen(base_graph, base_context):
    base_graph.nodes[0].metadata['nested'] = {'values': ['x']}
    snapshot = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    nested = snapshot.nodes[0].metadata['nested']
    try:
        nested['values'] = ()
    except TypeError:
        pass
    else:
        raise AssertionError('snapshot metadata should be immutable')


def test_parent_snapshot_participates_in_identity(base_graph, base_context):
    first = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    child = GraphSnapshot.capture(
        base_graph,
        semantic_context=base_context,
        parent_snapshot_id=first.snapshot_id,
    )
    assert first.graph_fingerprint == child.graph_fingerprint
    assert first.snapshot_id != child.snapshot_id


def test_snapshot_metadata_participates_in_identity(base_graph, base_context):
    first = GraphSnapshot.capture(base_graph, semantic_context=base_context, metadata={'revision': '1'})
    second = GraphSnapshot.capture(base_graph, semantic_context=base_context, metadata={'revision': '2'})
    assert first.snapshot_id != second.snapshot_id

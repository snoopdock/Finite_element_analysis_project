from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import (
    ArtifactValidity,
    AuditArtifactDependencyIndex,
    GraphSnapshot,
    compare_snapshots,
    propagate_impacts,
)
from audit_engine.semantic_audit.findings.models import AuditFinding


def _report(before_graph, after_graph, context, artifacts):
    before = GraphSnapshot.capture(before_graph, semantic_context=context)
    after = GraphSnapshot.capture(after_graph, semantic_context=context, parent_snapshot_id=before.snapshot_id)
    delta = compare_snapshots(before, after)
    return propagate_impacts(
        before=before,
        after=after,
        delta=delta,
        dependency_index=AuditArtifactDependencyIndex.build(artifacts),
    )


def _finding(receipt):
    return AuditFinding(
        finding_id='finding:g321', rule_id='r', rule_version='1', receipt_id=receipt.receipt_id,
        obligation_id=receipt.obligation_id, severity='critical', title='t', message='m',
        evidence_ids=receipt.evidence_ids, graph_fingerprint=receipt.graph_fingerprint,
        semantic_context_fingerprint=receipt.semantic_context_fingerprint,
    )


def test_unrelated_distant_node_change_stays_current(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = copy_graph(base_graph)
    after.add_node(SemanticNode('remote', 'Module'))
    report = _report(base_graph, after, base_context, [result, receipt])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.CURRENT
    assert report.by_id(receipt.receipt_id).validity is ArtifactValidity.CURRENT


def test_edge_added_to_known_neighborhood_requires_recheck(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = copy_graph(base_graph)
    after.add_edge(SemanticEdge('a', 'c', 'DEPENDS_ON'))
    report = _report(base_graph, after, base_context, [result, receipt])
    analysis_impact = report.by_id(result.analysis_id)
    assert analysis_impact.validity is ArtifactValidity.RECHECK_REQUIRED
    assert 'relevant_neighborhood_changed' in analysis_impact.reasons
    assert report.by_id(receipt.receipt_id).validity is ArtifactValidity.RECHECK_REQUIRED


def test_irrelevant_relation_addition_does_not_recheck_filtered_dependency(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context, constraints={'max_depth': 1, 'relation_types': ['DEPENDS_ON']})
    after = copy_graph(base_graph)
    after.add_edge(SemanticEdge('b', 'c', 'DOCUMENTS'))
    report = _report(base_graph, after, base_context, [result, receipt])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.CURRENT


def test_removed_supporting_edge_stales_chain(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = _finding(receipt)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    report = _report(base_graph, after, base_context, [result, receipt, finding])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.STALE
    assert report.by_id(receipt.receipt_id).validity is ArtifactValidity.STALE
    assert report.by_id(finding.finding_id).validity is ArtifactValidity.STALE


def test_removed_source_node_stales_analysis(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = SemanticGraph()
    after.add_node(SemanticNode('b', 'Module', {'lifecycle': 'stable'}))
    after.add_node(SemanticNode('c', 'Module'))
    report = _report(base_graph, after, base_context, [result, receipt])
    impact = report.by_id(result.analysis_id)
    assert impact.validity is ArtifactValidity.STALE
    assert 'source_entity_removed' in impact.reasons


def test_modified_referenced_node_requires_recheck(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = copy_graph(base_graph)
    after.get_node('b').attributes['lifecycle'] = 'deprecated'
    report = _report(base_graph, after, base_context, [result, receipt])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.RECHECK_REQUIRED
    assert report.by_id(receipt.receipt_id).validity is ArtifactValidity.RECHECK_REQUIRED


def test_missing_upstream_for_receipt_requires_recheck(base_graph, base_context, copy_graph, analysis_receipt_factory):
    _, receipt = analysis_receipt_factory(base_graph, base_context)
    after = copy_graph(base_graph)
    after.add_node(SemanticNode('remote', 'Module'))
    report = _report(base_graph, after, base_context, [receipt])
    impact = report.by_id(receipt.receipt_id)
    assert impact.validity is ArtifactValidity.RECHECK_REQUIRED
    assert 'upstream_artifact_unavailable' in impact.reasons



def test_edge_beyond_max_depth_does_not_force_recheck(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context, constraints={'max_depth': 1, 'relation_types': ['DEPENDS_ON']})
    after = copy_graph(base_graph)
    after.add_edge(SemanticEdge('b', 'c', 'DEPENDS_ON'))
    report = _report(base_graph, after, base_context, [result, receipt])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.CURRENT
    assert report.by_id(receipt.receipt_id).validity is ArtifactValidity.CURRENT


def test_removing_one_duplicate_observed_edge_keeps_analysis_current(base_context, analysis_receipt_factory):
    graph = SemanticGraph()
    graph.add_node(SemanticNode('a', 'Module'))
    graph.add_node(SemanticNode('b', 'Module'))
    graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'same'}))
    graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'same'}))
    result, receipt = analysis_receipt_factory(graph, base_context)
    after = SemanticGraph()
    after.add_node(SemanticNode('a', 'Module'))
    after.add_node(SemanticNode('b', 'Module'))
    after.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'same'}))
    report = _report(graph, after, base_context, [result, receipt])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.CURRENT
    assert report.by_id(receipt.receipt_id).validity is ArtifactValidity.CURRENT

def test_noop_keeps_complete_chain_current(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = _finding(receipt)
    report = _report(base_graph, copy_graph(base_graph), base_context, [result, receipt, finding])
    assert set(item.validity for item in report.impacts) == {ArtifactValidity.CURRENT}


def test_unfiltered_structural_analysis_treats_new_relation_type_as_relevant(base_graph, base_context, copy_graph, analysis_receipt_factory):
    from audit_engine.semantic_audit.graph.queries import QueryType
    result, receipt = analysis_receipt_factory(
        base_graph,
        base_context,
        query_id='structural-wildcard',
        query_type=QueryType.STRUCTURAL,
        constraints={},
    )
    after = copy_graph(base_graph)
    after.add_edge(SemanticEdge('a', 'c', 'CALLS'))
    report = _report(base_graph, after, base_context, [result, receipt])
    assert report.by_id(result.analysis_id).validity is ArtifactValidity.RECHECK_REQUIRED

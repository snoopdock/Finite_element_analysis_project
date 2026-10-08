from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import ArtifactValidity, GraphSnapshot, assess_transition, compare_snapshots
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import ObservationContractVerifier, VerifierRegistry, VerificationObligation, VerificationService


def _analysis_and_receipt(graph, context):
    result = SemanticGraphAnalysisService(graph, semantic_context=context).analyze(
        GraphQuery('evolution-test', QueryType.DEPENDENCY, ['a'], {'max_depth': 1})
    )
    observation = result.observations[0]
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type='observation_contract',
        observation_ids=[observation.observation_id],
        evidence_ids=list(observation.evidence_ids),
        requested_verifier_ids=['observation-contract'],
        parameters={'subject_id': 'a', 'predicate': 'DEPENDS_ON', 'object_id': 'b'},
    )
    registry = VerifierRegistry()
    registry.register(ObservationContractVerifier())
    receipt = VerificationService(registry).verify(obligation, result, verifier_id='observation-contract')
    return result, receipt


def _copy_graph(graph):
    new = SemanticGraph()
    for node in graph.nodes:
        new.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    for edge in graph.edges:
        new.add_edge(SemanticEdge(edge.source_id, edge.target_id, edge.relation_type, dict(edge.attributes), dict(edge.metadata)))
    return new


def test_unchanged_state_keeps_artifacts_current(base_graph, base_context):
    result, receipt = _analysis_and_receipt(base_graph, base_context)
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after = GraphSnapshot.capture(_copy_graph(base_graph), semantic_context=base_context)
    report = assess_transition(before=before, after=after, delta=compare_snapshots(before, after), artifacts=[result, receipt])
    assert {item.validity for item in report.artifacts} == {ArtifactValidity.CURRENT}


def test_removed_direct_evidence_marks_artifacts_stale(base_graph, base_context):
    result, receipt = _analysis_and_receipt(base_graph, base_context)
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after_graph = SemanticGraph()
    for node in base_graph.nodes:
        after_graph.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    report = assess_transition(before=before, after=after, delta=compare_snapshots(before, after), artifacts=[result, receipt])
    assert all(item.validity is ArtifactValidity.STALE for item in report.artifacts)
    assert all('supporting_evidence_removed' in item.reasons for item in report.artifacts)


def test_unrelated_graph_change_requires_recheck(base_graph, base_context):
    result, receipt = _analysis_and_receipt(base_graph, base_context)
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after_graph = _copy_graph(base_graph)
    after_graph.add_node(SemanticNode('d', 'Module'))
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    report = assess_transition(before=before, after=after, delta=compare_snapshots(before, after), artifacts=[receipt])
    assert report.artifacts[0].validity is ArtifactValidity.RECHECK_REQUIRED


def test_semantic_context_change_marks_artifact_stale(base_graph, base_context):
    result, receipt = _analysis_and_receipt(base_graph, base_context)
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    changed = type(base_context)(
        graph_schema_version=base_context.graph_schema_version,
        relationship_vocabulary_version='repo-relations/v2',
        projection_contract_version=base_context.projection_contract_version,
        analysis_contract_version=base_context.analysis_contract_version,
    )
    after = GraphSnapshot.capture(_copy_graph(base_graph), semantic_context=changed)
    report = assess_transition(before=before, after=after, delta=compare_snapshots(before, after), artifacts=[receipt])
    assert report.artifacts[0].validity is ArtifactValidity.STALE
    assert report.artifacts[0].reasons == ('semantic_context_changed',)


def test_artifact_bound_to_wrong_before_snapshot_is_stale(base_graph, base_context):
    result, receipt = _analysis_and_receipt(base_graph, base_context)
    other = _copy_graph(base_graph)
    other.add_node(SemanticNode('x', 'Module'))
    before = GraphSnapshot.capture(other, semantic_context=base_context)
    after = GraphSnapshot.capture(other, semantic_context=base_context)
    report = assess_transition(before=before, after=after, delta=compare_snapshots(before, after), artifacts=[receipt])
    assert report.artifacts[0].validity is ArtifactValidity.STALE
    assert report.artifacts[0].reasons == ('artifact_not_bound_to_before_snapshot',)


def test_removing_one_duplicate_edge_does_not_claim_evidence_disappeared(base_context):
    graph = SemanticGraph()
    graph.add_node(SemanticNode('a', 'Module'))
    graph.add_node(SemanticNode('b', 'Module'))
    graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'same'}))
    graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'same'}))
    result, receipt = _analysis_and_receipt(graph, base_context)
    before = GraphSnapshot.capture(graph, semantic_context=base_context)
    after_graph = SemanticGraph()
    after_graph.add_node(SemanticNode('a', 'Module'))
    after_graph.add_node(SemanticNode('b', 'Module'))
    after_graph.add_edge(SemanticEdge('a', 'b', 'DEPENDS_ON', metadata={'source_id': 'same'}))
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    delta = compare_snapshots(before, after)
    report = assess_transition(before=before, after=after, delta=delta, artifacts=[receipt])
    assert report.artifacts[0].validity is ArtifactValidity.RECHECK_REQUIRED
    assert 'supporting_evidence_removed' not in report.artifacts[0].reasons


def test_verified_finding_becomes_stale_when_its_edge_evidence_is_removed(base_graph, base_context):
    from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
    from audit_engine.semantic_audit.verification import GraphAttributeConstraintVerifier

    result = SemanticGraphAnalysisService(base_graph, semantic_context=base_context).analyze(
        GraphQuery('finding-evolution-test', QueryType.DEPENDENCY, ['a'], {'max_depth': 1})
    )
    # Make target satisfy the repository architecture example rule.
    base_graph.get_node('b').attributes['lifecycle'] = 'experimental'
    # Re-analyze after semantic mutation so the graph fingerprint is correctly bound.
    result = SemanticGraphAnalysisService(base_graph, semantic_context=base_context).analyze(
        GraphQuery('finding-evolution-test-2', QueryType.DEPENDENCY, ['a'], {'max_depth': 1})
    )
    registry = VerifierRegistry()
    registry.register(GraphAttributeConstraintVerifier())
    execution = DomainRuleExecutor(VerificationService(registry)).execute(
        DomainRuleLoader.from_yaml('specs/rules/architecture/no_production_to_experimental_dependency.yaml'),
        result,
        base_graph,
    )
    assert len(execution.findings) == 1
    finding = execution.findings[0]
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after_graph = SemanticGraph()
    for node in base_graph.nodes:
        after_graph.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    report = assess_transition(before=before, after=after, delta=compare_snapshots(before, after), artifacts=[finding])
    assert report.artifacts[0].validity is ArtifactValidity.STALE
    assert report.artifacts[0].affected_evidence_ids == finding.evidence_ids

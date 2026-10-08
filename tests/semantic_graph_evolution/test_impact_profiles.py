from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticNode
from audit_engine.semantic_audit.evolution import (
    AuditArtifactDependencyIndex,
    ChangeKind,
    GraphSnapshot,
    ImpactScope,
    changes_from_delta,
    compare_snapshots,
    profile_analysis,
    profile_receipt,
)
from audit_engine.semantic_audit.findings.models import AuditFinding
from audit_engine.semantic_audit.graph.queries import QueryType


def test_delta_is_normalized_into_change_atoms(base_graph, base_context, copy_graph):
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after_graph = copy_graph(base_graph)
    after_graph.add_node(SemanticNode('d', 'Module'))
    after_graph.add_edge(SemanticEdge('b', 'd', 'DEPENDS_ON'))
    after = GraphSnapshot.capture(after_graph, semantic_context=base_context)
    atoms = changes_from_delta(compare_snapshots(before, after))
    assert {atom.kind for atom in atoms} == {ChangeKind.NODE_ADDED, ChangeKind.EDGE_ADDED}
    assert any(atom.node_ids == ('b', 'd') for atom in atoms if atom.kind is ChangeKind.EDGE_ADDED)


def test_context_change_becomes_explicit_change_atom(base_graph, base_context):
    changed = type(base_context)(
        graph_schema_version=base_context.graph_schema_version,
        relationship_vocabulary_version='repo-relations/v2',
        projection_contract_version=base_context.projection_contract_version,
        analysis_contract_version=base_context.analysis_contract_version,
    )
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after = GraphSnapshot.capture(base_graph, semantic_context=changed)
    atoms = changes_from_delta(compare_snapshots(before, after))
    atom = next(item for item in atoms if item.kind is ChangeKind.SEMANTIC_CONTEXT_CHANGED)
    assert atom.semantic_context_fields == ('relationship_vocabulary_version',)


def test_dependency_analysis_profile_is_local(base_graph, base_context, analysis_receipt_factory):
    result, _ = analysis_receipt_factory(base_graph, base_context)
    profile = profile_analysis(result)
    assert profile.impact_scope is ImpactScope.LOCAL_NEIGHBORHOOD
    assert set(profile.node_ids) == {'a', 'b'}
    assert profile.source_node_ids == ('a',)
    assert 'DEPENDS_ON' in profile.relation_types


def test_path_analysis_profile_tracks_target(base_graph, base_context, analysis_receipt_factory):
    result, _ = analysis_receipt_factory(
        base_graph,
        base_context,
        query_id='path-profile',
        query_type=QueryType.PATH,
        constraints={'target_entity': 'b', 'max_depth': 4},
    )
    profile = profile_analysis(result)
    assert profile.impact_scope is ImpactScope.PATH_FRONTIER
    assert 'b' in profile.node_ids


def test_receipt_profile_points_to_source_analysis(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    profile = profile_receipt(receipt)
    assert profile.upstream_artifact_ids == (result.analysis_id,)
    assert set(profile.evidence_ids) == set(receipt.evidence_ids)


def test_dependency_index_builds_analysis_receipt_finding_chain(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = AuditFinding(
        finding_id='finding:test', rule_id='r', rule_version='1', receipt_id=receipt.receipt_id,
        obligation_id=receipt.obligation_id, severity='high', title='t', message='m',
        evidence_ids=receipt.evidence_ids, graph_fingerprint=receipt.graph_fingerprint,
        semantic_context_fingerprint=receipt.semantic_context_fingerprint,
    )
    index = AuditArtifactDependencyIndex.build([finding, receipt, result])
    assert index.downstream_of(result.analysis_id) == tuple(sorted((receipt.receipt_id, finding.finding_id)))
    assert index.unresolved_upstream_ids() == ()


def test_dependency_index_reports_missing_upstream(base_graph, base_context, analysis_receipt_factory):
    _, receipt = analysis_receipt_factory(base_graph, base_context)
    index = AuditArtifactDependencyIndex.build([receipt])
    assert index.unresolved_upstream_ids() == (receipt.source_analysis_id,)


def test_profile_identity_collision_is_rejected(base_graph, base_context, analysis_receipt_factory):
    result, _ = analysis_receipt_factory(base_graph, base_context)
    index = AuditArtifactDependencyIndex.build([result])
    profile = profile_analysis(result)
    from dataclasses import replace
    bad = replace(profile, graph_fingerprint='graph:different')
    try:
        index.add_profile(bad)
    except ValueError as exc:
        assert 'identity collision' in str(exc)
    else:
        raise AssertionError('Expected dependency identity collision.')


def test_graph_attribute_receipt_profile_captures_checked_nodes(base_graph, base_context):
    from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
    from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
    from audit_engine.semantic_audit.verification import (
        GraphAttributeConstraintVerifier,
        VerificationObligation,
        VerificationService,
        VerifierRegistry,
    )
    result = SemanticGraphAnalysisService(base_graph, semantic_context=base_context).analyze(
        GraphQuery('attribute-profile', QueryType.DEPENDENCY, ['a'], {'max_depth': 1})
    )
    observation = result.observations[0]
    obligation = VerificationObligation.from_analysis_result(
        result,
        obligation_type='graph_attribute_constraint',
        observation_ids=[observation.observation_id],
        evidence_ids=list(observation.evidence_ids),
        requested_verifier_ids=['graph-attribute-constraint'],
        parameters={'source_attributes': {'lifecycle': 'production'}},
    )
    registry = VerifierRegistry()
    registry.register(GraphAttributeConstraintVerifier())
    receipt = VerificationService(registry).verify(
        obligation, result, verifier_id='graph-attribute-constraint', semantic_graph=base_graph
    )
    profile = profile_receipt(receipt)
    assert set(profile.node_ids) == {'a', 'b'}

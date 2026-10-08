from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import (
    ArtifactValidity,
    AuditArtifactDependencyIndex,
    GraphSnapshot,
    PriorityBand,
    ReverificationAction,
    ReverificationPolicy,
    build_reverification_plan,
    compare_snapshots,
    propagate_impacts,
)
from audit_engine.semantic_audit.findings.models import AuditFinding


def _finding(receipt, severity='critical'):
    return AuditFinding(
        finding_id='finding:plan', rule_id='r', rule_version='1', receipt_id=receipt.receipt_id,
        obligation_id=receipt.obligation_id, severity=severity, title='t', message='m',
        evidence_ids=receipt.evidence_ids, graph_fingerprint=receipt.graph_fingerprint,
        semantic_context_fingerprint=receipt.semantic_context_fingerprint,
    )


def _plan(base_graph, after_graph, context, artifacts):
    before = GraphSnapshot.capture(base_graph, semantic_context=context)
    after = GraphSnapshot.capture(after_graph, semantic_context=context, parent_snapshot_id=before.snapshot_id)
    index = AuditArtifactDependencyIndex.build(artifacts)
    report = propagate_impacts(before=before, after=after, delta=compare_snapshots(before, after), dependency_index=index)
    return build_reverification_plan(report=report, dependency_index=index, artifacts=artifacts)


def test_current_artifacts_create_no_tasks(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    plan = _plan(base_graph, copy_graph(base_graph), base_context, [result, receipt])
    assert plan.is_empty


def test_actions_are_specific_to_artifact_stage(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = _finding(receipt)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    plan = _plan(base_graph, after, base_context, [result, receipt, finding])
    actions = {task.artifact_type: task.action for task in plan.tasks}
    assert actions['analysis'] is ReverificationAction.RERUN_ANALYSIS
    assert actions['verification_receipt'] is ReverificationAction.REVERIFY_RECEIPT
    assert actions['finding'] is ReverificationAction.REEVALUATE_FINDING


def test_receipt_and_finding_keep_upstream_prerequisites(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = _finding(receipt)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    plan = _plan(base_graph, after, base_context, [result, receipt, finding])
    by_type = {task.artifact_type: task for task in plan.tasks}
    assert by_type['verification_receipt'].prerequisite_artifact_ids == (result.analysis_id,)
    assert by_type['finding'].prerequisite_artifact_ids == (receipt.receipt_id,)


def test_critical_finding_receives_higher_priority_than_analysis(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = _finding(receipt, 'critical')
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    plan = _plan(base_graph, after, base_context, [result, receipt, finding])
    scores = {task.artifact_type: task.priority_score for task in plan.tasks}
    assert scores['finding'] > scores['analysis']


def test_stale_task_scores_above_recheck_with_same_artifact_class(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after_recheck = copy_graph(base_graph)
    after_recheck.add_edge(SemanticEdge('a', 'c', 'DEPENDS_ON'))
    recheck_plan = _plan(base_graph, after_recheck, base_context, [result, receipt])
    recheck = next(task for task in recheck_plan.tasks if task.artifact_type == 'analysis')

    after_stale = SemanticGraph()
    for node in base_graph.nodes:
        after_stale.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    stale_plan = _plan(base_graph, after_stale, base_context, [result, receipt])
    stale = next(task for task in stale_plan.tasks if task.artifact_type == 'analysis')
    assert stale.validity is ArtifactValidity.STALE
    assert stale.priority_score > recheck.priority_score


def test_plan_identity_is_deterministic(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    one = _plan(base_graph, after, base_context, [result, receipt])
    two = _plan(base_graph, after, base_context, [result, receipt])
    assert one.plan_id == two.plan_id
    assert [task.task_id for task in one.tasks] == [task.task_id for task in two.tasks]


def test_policy_version_participates_in_plan_identity(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    before = GraphSnapshot.capture(base_graph, semantic_context=base_context)
    after_snapshot = GraphSnapshot.capture(after, semantic_context=base_context, parent_snapshot_id=before.snapshot_id)
    index = AuditArtifactDependencyIndex.build([result, receipt])
    report = propagate_impacts(before=before, after=after_snapshot, delta=compare_snapshots(before, after_snapshot), dependency_index=index)
    one = build_reverification_plan(report=report, dependency_index=index, artifacts=[result, receipt])
    two = build_reverification_plan(report=report, dependency_index=index, artifacts=[result, receipt], policy=ReverificationPolicy(version='incremental_reverification_policy/v2'))
    assert one.plan_id != two.plan_id


def test_priority_band_is_explicit_not_semantic_truth(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    plan = _plan(base_graph, after, base_context, [result, receipt])
    assert all(isinstance(task.priority_band, PriorityBand) for task in plan.tasks)

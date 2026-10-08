from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.evolution import (
    ArtifactValidity,
    IncrementalReverificationService,
    SemanticGraphEvolutionService,
)
from audit_engine.semantic_audit.findings.models import AuditFinding


def _finding(receipt):
    return AuditFinding(
        finding_id='finding:service', rule_id='rule', rule_version='1', receipt_id=receipt.receipt_id,
        obligation_id=receipt.obligation_id, severity='high', title='t', message='m',
        evidence_ids=receipt.evidence_ids, graph_fingerprint=receipt.graph_fingerprint,
        semantic_context_fingerprint=receipt.semantic_context_fingerprint,
    )


def test_incremental_service_combines_impact_and_plan(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = copy_graph(base_graph)
    after.add_edge(SemanticEdge('a', 'c', 'DEPENDS_ON'))
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=base_graph, after_graph=after, before_context=base_context,
    )
    incremental = IncrementalReverificationService().assess(
        evolution=evolution, artifacts=[result, receipt]
    )
    assert incremental.impact_report.by_id(result.analysis_id).validity is ArtifactValidity.RECHECK_REQUIRED
    assert not incremental.reverification_plan.is_empty


def test_incremental_service_avoids_tasks_for_irrelevant_change(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    after = copy_graph(base_graph)
    after.add_node(SemanticNode('remote', 'Module'))
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=base_graph, after_graph=after, before_context=base_context,
    )
    incremental = IncrementalReverificationService().assess(
        evolution=evolution, artifacts=[result, receipt]
    )
    assert incremental.reverification_plan.is_empty


def test_incremental_service_propagates_evidence_loss_to_finding(base_graph, base_context, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    finding = _finding(receipt)
    after = SemanticGraph()
    for node in base_graph.nodes:
        after.add_node(SemanticNode(node.node_id, node.entity_type, dict(node.attributes), dict(node.metadata)))
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=base_graph, after_graph=after, before_context=base_context,
    )
    incremental = IncrementalReverificationService().assess(
        evolution=evolution, artifacts=[result, receipt, finding]
    )
    assert incremental.impact_report.by_id(finding.finding_id).validity is ArtifactValidity.STALE
    assert any(task.artifact_id == finding.finding_id for task in incremental.reverification_plan.tasks)


def test_incremental_result_is_serializable(base_graph, base_context, copy_graph, analysis_receipt_factory):
    result, receipt = analysis_receipt_factory(base_graph, base_context)
    evolution = SemanticGraphEvolutionService().compare(
        before_graph=base_graph, after_graph=copy_graph(base_graph), before_context=base_context,
    )
    payload = IncrementalReverificationService().assess(
        evolution=evolution, artifacts=[result, receipt]
    ).to_dict()
    assert payload['schema_version'] == 'semantic_incremental_reverification/v1'
    assert 'impact_report' in payload and 'reverification_plan' in payload

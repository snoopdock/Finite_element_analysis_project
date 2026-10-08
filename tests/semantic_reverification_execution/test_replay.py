from audit_engine.semantic_audit.evolution import (
    ReplaySelectionMode,
    ReplayStatus,
    graph_query_from_analysis,
    rebase_verification_obligation,
    replay_analysis,
)
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import QueryType
from .helpers import make_graph


def test_graph_query_is_reconstructed_from_analysis(audit_chain):
    _, analysis, _, _, _ = audit_chain
    query = graph_query_from_analysis(analysis)
    assert query.query_id == analysis.query_id
    assert query.query_type is QueryType.DEPENDENCY
    assert query.source_entities == analysis.source_entities
    assert query.constraints["max_depth"] == 1


def test_analysis_replay_binds_after_graph(semantic_context, audit_chain):
    _, analysis, _, _, _ = audit_chain
    after = make_graph(add_extra=True)
    replay = replay_analysis(analysis, graph=after, semantic_context=semantic_context)
    assert replay.status is ReplayStatus.REPLAYED
    assert replay.analysis.graph_fingerprint != analysis.graph_fingerprint


def test_analysis_replay_reports_removed_source(semantic_context, audit_chain):
    _, analysis, _, _, _ = audit_chain
    after = make_graph()
    after.nodes[:] = [node for node in after.nodes if node.node_id != "prod"]
    after.edges[:] = []
    replay = replay_analysis(analysis, graph=after, semantic_context=semantic_context)
    assert replay.status is ReplayStatus.SOURCE_NO_LONGER_PRESENT
    assert replay.analysis is None


def test_exact_rebase_rejects_changed_evidence_identity(semantic_context, audit_chain):
    _, analysis, execution, _, _ = audit_chain
    after = make_graph(edge_source="code:changed")
    successor = SemanticGraphAnalysisService(after, semantic_context=semantic_context).analyze(
        graph_query_from_analysis(analysis)
    )
    result = rebase_verification_obligation(
        execution.obligations[0], predecessor_analysis=analysis, successor_analysis=successor,
        selection_mode=ReplaySelectionMode.EXACT_IDS,
    )
    assert result.status is ReplayStatus.TARGET_NO_LONGER_PRESENT


def test_semantic_observation_rebase_accepts_changed_edge_provenance(semantic_context, audit_chain):
    _, analysis, execution, _, _ = audit_chain
    after = make_graph(edge_source="code:changed")
    successor = SemanticGraphAnalysisService(after, semantic_context=semantic_context).analyze(
        graph_query_from_analysis(analysis)
    )
    result = rebase_verification_obligation(
        execution.obligations[0], predecessor_analysis=analysis, successor_analysis=successor,
        selection_mode=ReplaySelectionMode.OBSERVATION_SEMANTICS,
    )
    assert result.status is ReplayStatus.REPLAYED
    assert result.obligation.evidence_ids != execution.obligations[0].evidence_ids


def test_semantic_rebase_reports_removed_observation(semantic_context, audit_chain):
    _, analysis, execution, _, _ = audit_chain
    after = make_graph(remove_edge=True)
    successor = SemanticGraphAnalysisService(after, semantic_context=semantic_context).analyze(
        graph_query_from_analysis(analysis)
    )
    result = rebase_verification_obligation(
        execution.obligations[0], predecessor_analysis=analysis, successor_analysis=successor,
        selection_mode=ReplaySelectionMode.OBSERVATION_SEMANTICS,
    )
    assert result.status is ReplayStatus.TARGET_NO_LONGER_PRESENT


def test_analysis_scope_reselects_current_analysis(semantic_context, audit_chain):
    _, analysis, execution, _, _ = audit_chain
    after = make_graph(add_extra=True)
    successor = SemanticGraphAnalysisService(after, semantic_context=semantic_context).analyze(
        graph_query_from_analysis(analysis)
    )
    result = rebase_verification_obligation(
        execution.obligations[0], predecessor_analysis=analysis, successor_analysis=successor,
        selection_mode=ReplaySelectionMode.ANALYSIS_SCOPE,
    )
    assert result.status is ReplayStatus.REPLAYED
    assert set(result.obligation.observation_ids) == {item.observation_id for item in successor.observations}

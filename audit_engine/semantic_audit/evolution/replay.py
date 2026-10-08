"""Replay contracts for incremental semantic re-verification.

Replay reconstructs explicit prior audit intent against a new canonical graph
state. It does not infer hidden selector semantics and does not create findings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import GraphAnalysisResult, SemanticContext
from audit_engine.semantic_audit.graph.analysis.models import AnalysisType
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.verification import VerificationObligation


REPLAY_SCHEMA_VERSION = "semantic_reverification_replay/v1"


class ReplaySelectionMode(str, Enum):
    EXACT_IDS = "exact_ids"
    OBSERVATION_SEMANTICS = "observation_semantics"
    ANALYSIS_SCOPE = "analysis_scope"


class ReplayStatus(str, Enum):
    REPLAYED = "replayed"
    TARGET_NO_LONGER_PRESENT = "target_no_longer_present"
    SOURCE_NO_LONGER_PRESENT = "source_no_longer_present"


@dataclass(frozen=True)
class AnalysisReplayResult:
    status: ReplayStatus
    predecessor_analysis_id: str
    analysis: GraphAnalysisResult | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "predecessor_analysis_id": self.predecessor_analysis_id,
            "successor_analysis_id": self.analysis.analysis_id if self.analysis else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ObligationReplayResult:
    status: ReplayStatus
    predecessor_obligation_id: str
    obligation: VerificationObligation | None = None
    reason: str = ""
    selection_mode: ReplaySelectionMode = ReplaySelectionMode.EXACT_IDS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "predecessor_obligation_id": self.predecessor_obligation_id,
            "successor_obligation_id": self.obligation.obligation_id if self.obligation else None,
            "reason": self.reason,
            "selection_mode": self.selection_mode.value,
        }


def graph_query_from_analysis(result: GraphAnalysisResult) -> GraphQuery:
    mapping = {
        AnalysisType.STRUCTURAL: QueryType.STRUCTURAL,
        AnalysisType.DEPENDENCY: QueryType.DEPENDENCY,
        AnalysisType.PATH: QueryType.PATH,
    }
    try:
        query_type = mapping[result.analysis_type]
    except KeyError as exc:
        raise ValueError(f"Analysis type is not replayable: {result.analysis_type!r}") from exc
    return GraphQuery(
        query_id=result.query_id,
        query_type=query_type,
        source_entities=result.source_entities,
        constraints=dict(result.parameters),
    )


def replay_analysis(
    predecessor: GraphAnalysisResult,
    *,
    graph: SemanticGraph,
    semantic_context: SemanticContext,
) -> AnalysisReplayResult:
    missing_sources = [node_id for node_id in predecessor.source_entities if not graph.has_node(node_id)]
    if missing_sources:
        return AnalysisReplayResult(
            ReplayStatus.SOURCE_NO_LONGER_PRESENT,
            predecessor.analysis_id,
            reason="source_entities_absent:" + ",".join(sorted(missing_sources)),
        )
    if predecessor.analysis_type is AnalysisType.PATH:
        target = predecessor.parameters.get("target_entity")
        if isinstance(target, str) and target and not graph.has_node(target):
            return AnalysisReplayResult(
                ReplayStatus.TARGET_NO_LONGER_PRESENT,
                predecessor.analysis_id,
                reason=f"path_target_absent:{target}",
            )
    result = SemanticGraphAnalysisService(
        graph,
        semantic_context=semantic_context,
    ).analyze(graph_query_from_analysis(predecessor))
    return AnalysisReplayResult(
        ReplayStatus.REPLAYED,
        predecessor.analysis_id,
        analysis=result,
        reason="analysis_replayed_against_after_snapshot",
    )


def _observation_signature(observation) -> tuple[str, str, str]:
    return observation.subject_id, observation.predicate, observation.object_id


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def rebase_verification_obligation(
    predecessor: VerificationObligation,
    *,
    predecessor_analysis: GraphAnalysisResult,
    successor_analysis: GraphAnalysisResult,
    selection_mode: ReplaySelectionMode = ReplaySelectionMode.EXACT_IDS,
) -> ObligationReplayResult:
    if predecessor.source_analysis_id != predecessor_analysis.analysis_id:
        raise ValueError("Predecessor obligation is not bound to predecessor analysis.")

    if selection_mode is ReplaySelectionMode.ANALYSIS_SCOPE:
        obligation = VerificationObligation.from_analysis_result(
            successor_analysis,
            obligation_type=predecessor.obligation_type,
            requested_verifier_ids=predecessor.requested_verifier_ids,
            parameters=predecessor.parameters,
        )
        return ObligationReplayResult(
            ReplayStatus.REPLAYED,
            predecessor.obligation_id,
            obligation,
            "analysis_scope_reselected",
            selection_mode,
        )

    successor_observation_by_id = {item.observation_id: item for item in successor_analysis.observations}
    successor_evidence_ids = {item.evidence_id for item in successor_analysis.evidence}

    if selection_mode is ReplaySelectionMode.EXACT_IDS:
        missing = [value for value in predecessor.observation_ids if value not in successor_observation_by_id]
        missing.extend(value for value in predecessor.evidence_ids if value not in successor_evidence_ids)
        if missing:
            return ObligationReplayResult(
                ReplayStatus.TARGET_NO_LONGER_PRESENT,
                predecessor.obligation_id,
                reason="exact_replay_target_absent:" + ",".join(sorted(set(missing))),
                selection_mode=selection_mode,
            )
        obligation = VerificationObligation.from_analysis_result(
            successor_analysis,
            obligation_type=predecessor.obligation_type,
            observation_ids=predecessor.observation_ids,
            evidence_ids=predecessor.evidence_ids,
            requested_verifier_ids=predecessor.requested_verifier_ids,
            parameters=predecessor.parameters,
        )
        return ObligationReplayResult(
            ReplayStatus.REPLAYED,
            predecessor.obligation_id,
            obligation,
            "exact_selection_replayed",
            selection_mode,
        )

    if selection_mode is not ReplaySelectionMode.OBSERVATION_SEMANTICS:
        raise ValueError(f"Unsupported replay selection mode: {selection_mode!r}")

    predecessor_by_id = {item.observation_id: item for item in predecessor_analysis.observations}
    requested = []
    for observation_id in predecessor.observation_ids:
        observation = predecessor_by_id.get(observation_id)
        if observation is None:
            raise ValueError("Predecessor obligation references an unavailable observation.")
        requested.append(observation)

    successor_by_signature: dict[tuple[str, str, str], list] = {}
    for observation in successor_analysis.observations:
        successor_by_signature.setdefault(_observation_signature(observation), []).append(observation)

    selected_observation_ids: list[str] = []
    selected_evidence_ids: list[str] = []
    missing_signatures: list[str] = []
    for old_observation in requested:
        signature = _observation_signature(old_observation)
        matches = successor_by_signature.get(signature, ())
        if not matches:
            missing_signatures.append("|".join(signature))
            continue
        for match in matches:
            selected_observation_ids.append(match.observation_id)
            selected_evidence_ids.extend(match.evidence_ids)

    if missing_signatures:
        return ObligationReplayResult(
            ReplayStatus.TARGET_NO_LONGER_PRESENT,
            predecessor.obligation_id,
            reason="semantic_observation_absent:" + ",".join(sorted(missing_signatures)),
            selection_mode=selection_mode,
        )

    # Evidence-only obligations have no semantic observation selector. Preserve
    # exact evidence identity unless the caller explicitly used ANALYSIS_SCOPE.
    if not requested and predecessor.evidence_ids:
        missing = [value for value in predecessor.evidence_ids if value not in successor_evidence_ids]
        if missing:
            return ObligationReplayResult(
                ReplayStatus.TARGET_NO_LONGER_PRESENT,
                predecessor.obligation_id,
                reason="selected_evidence_absent:" + ",".join(sorted(missing)),
                selection_mode=selection_mode,
            )
        selected_evidence_ids.extend(predecessor.evidence_ids)

    obligation = VerificationObligation.from_analysis_result(
        successor_analysis,
        obligation_type=predecessor.obligation_type,
        observation_ids=_unique(selected_observation_ids),
        evidence_ids=_unique(selected_evidence_ids),
        requested_verifier_ids=predecessor.requested_verifier_ids,
        parameters=predecessor.parameters,
    )
    return ObligationReplayResult(
        ReplayStatus.REPLAYED,
        predecessor.obligation_id,
        obligation,
        "semantic_observation_reselected",
        selection_mode,
    )

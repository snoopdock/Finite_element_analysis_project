
"""Core G3.1 verification contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from audit_engine.semantic_audit.graph.analysis import (
    GraphAnalysisResult,
    VerificationStatus,
)
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id, graph_fingerprint


class VerificationDecision(str, Enum):
    """Outcome of testing one explicit verification obligation."""

    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


@dataclass(frozen=True)
class VerificationObligation:
    """A bounded hypothesis that requires an explicit verifier.

    Obligations bind analysis artifacts to the exact graph and semantic context
    under which they were produced. They do not themselves represent findings.
    """

    obligation_id: str
    obligation_type: str
    source_analysis_id: str
    observation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    graph_fingerprint: str
    semantic_context_fingerprint: str
    requested_verifier_ids: tuple[str, ...] = field(default_factory=tuple)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    state: VerificationStatus = VerificationStatus.PROPOSED

    @classmethod
    def from_analysis_result(
        cls,
        result: GraphAnalysisResult,
        *,
        obligation_type: str,
        observation_ids: Sequence[str] | None = None,
        evidence_ids: Sequence[str] | None = None,
        requested_verifier_ids: Sequence[str] | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> "VerificationObligation":
        obligation_type = str(obligation_type).strip()
        if not obligation_type:
            raise ValueError("obligation_type must be a non-empty string.")

        available_observation_ids = tuple(item.observation_id for item in result.observations)
        available_evidence_ids = tuple(item.evidence_id for item in result.evidence)
        available_observations = set(available_observation_ids)
        available_evidence = set(available_evidence_ids)
        selected_observations = tuple(
            dict.fromkeys(
                observation_ids if observation_ids is not None else available_observation_ids
            )
        )
        selected_evidence = tuple(
            dict.fromkeys(evidence_ids if evidence_ids is not None else available_evidence_ids)
        )

        missing_observations = sorted(set(selected_observations) - available_observations)
        missing_evidence = sorted(set(selected_evidence) - available_evidence)
        if missing_observations:
            raise ValueError(
                "Verification obligation references observations outside its source analysis: "
                + ", ".join(missing_observations)
            )
        if missing_evidence:
            raise ValueError(
                "Verification obligation references evidence outside its source analysis: "
                + ", ".join(missing_evidence)
            )

        requested = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in (requested_verifier_ids or ())
                if str(value).strip()
            )
        )
        params = dict(parameters or {})
        payload = {
            "obligation_type": obligation_type,
            "source_analysis_id": result.analysis_id,
            "observation_ids": sorted(selected_observations),
            "evidence_ids": sorted(selected_evidence),
            "graph_fingerprint": result.graph_fingerprint,
            "semantic_context_fingerprint": result.semantic_context.fingerprint,
            "requested_verifier_ids": list(requested),
            "parameters": params,
        }
        return cls(
            obligation_id=deterministic_id("obligation", payload, length=24),
            obligation_type=obligation_type,
            source_analysis_id=result.analysis_id,
            observation_ids=selected_observations,
            evidence_ids=selected_evidence,
            graph_fingerprint=result.graph_fingerprint,
            semantic_context_fingerprint=result.semantic_context.fingerprint,
            requested_verifier_ids=requested,
            parameters=params,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "obligation_type": self.obligation_type,
            "source_analysis_id": self.source_analysis_id,
            "observation_ids": list(self.observation_ids),
            "evidence_ids": list(self.evidence_ids),
            "graph_fingerprint": self.graph_fingerprint,
            "semantic_context_fingerprint": self.semantic_context_fingerprint,
            "requested_verifier_ids": list(self.requested_verifier_ids),
            "parameters": dict(self.parameters),
            "state": self.state.value,
        }


@dataclass(frozen=True)
class VerificationContext:
    """Read-only source material supplied to a verifier.

    ``semantic_graph`` is optional for backward compatibility with G3.1.0
    verifiers that operate entirely on analysis artifacts. Domain verifiers in
    G3.1.1 may require the canonical graph and must call :meth:`require_graph`
    rather than assuming one is present.
    """

    analysis_result: GraphAnalysisResult
    semantic_graph: SemanticGraph | None = None

    def validate_obligation_binding(self, obligation: VerificationObligation) -> None:
        result = self.analysis_result
        if obligation.source_analysis_id != result.analysis_id:
            raise ValueError("Verification obligation is bound to a different analysis result.")
        if obligation.graph_fingerprint != result.graph_fingerprint:
            raise ValueError("Verification obligation graph fingerprint does not match analysis result.")
        if obligation.semantic_context_fingerprint != result.semantic_context.fingerprint:
            raise ValueError("Verification obligation semantic context does not match analysis result.")
        observation_ids = {item.observation_id for item in result.observations}
        evidence_ids = {item.evidence_id for item in result.evidence}
        if not set(obligation.observation_ids).issubset(observation_ids):
            raise ValueError("Verification obligation references unavailable observations.")
        if not set(obligation.evidence_ids).issubset(evidence_ids):
            raise ValueError("Verification obligation references unavailable evidence.")
        if self.semantic_graph is not None:
            actual_graph_fingerprint = graph_fingerprint(self.semantic_graph)
            if actual_graph_fingerprint != result.graph_fingerprint:
                raise ValueError(
                    "Verification context graph fingerprint does not match analysis result."
                )

    def require_graph(self) -> SemanticGraph:
        if self.semantic_graph is None:
            raise ValueError(
                "This verifier requires the canonical SemanticGraph in its verification context."
            )
        return self.semantic_graph

    def all_observations(self):
        return tuple(self.analysis_result.observations)

    def all_evidence(self):
        return tuple(self.analysis_result.evidence)

    def selected_observations(self, obligation: VerificationObligation):
        wanted = set(obligation.observation_ids)
        return tuple(
            item for item in self.analysis_result.observations
            if item.observation_id in wanted
        )

    def selected_evidence(self, obligation: VerificationObligation):
        wanted = set(obligation.evidence_ids)
        return tuple(
            item for item in self.analysis_result.evidence
            if item.evidence_id in wanted
        )


@dataclass(frozen=True)
class VerificationAttempt:
    """One verifier execution before it is sealed into an immutable receipt."""

    attempt_id: str
    obligation_id: str
    verifier_id: str
    verifier_version: str
    decision: VerificationDecision
    evidence_state: VerificationStatus
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    details: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        obligation_id: str,
        verifier_id: str,
        verifier_version: str,
        decision: VerificationDecision,
        evidence_state: VerificationStatus,
        evidence_ids: Sequence[str] = (),
        details: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> "VerificationAttempt":
        payload = {
            "obligation_id": obligation_id,
            "verifier_id": verifier_id,
            "verifier_version": verifier_version,
            "decision": decision.value,
            "evidence_state": evidence_state.value,
            "evidence_ids": sorted(set(evidence_ids)),
            "details": dict(details or {}),
            "error": error,
        }
        return cls(
            attempt_id=deterministic_id("verification-attempt", payload, length=24),
            obligation_id=obligation_id,
            verifier_id=verifier_id,
            verifier_version=verifier_version,
            decision=decision,
            evidence_state=evidence_state,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            details=dict(details or {}),
            error=error,
        )

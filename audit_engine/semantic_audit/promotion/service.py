"""Guarded promotion of verified candidate relations into a canonical graph."""

from __future__ import annotations

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import edge_fingerprint, graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification import (
    CandidateKnowledge,
    VerificationDecision,
    VerificationObligation,
    VerificationReceipt,
)

from .models import CandidatePromotionPolicy, CandidatePromotionResult


_STATE_RANK = {
    VerificationStatus.PROPOSED: 0,
    VerificationStatus.OBSERVED: 1,
    VerificationStatus.CORROBORATED: 2,
    VerificationStatus.VALIDATED: 3,
}


class CandidatePromotionService:
    """Promote only candidates explicitly bound to a confirmed receipt.

    The service mutates only the target canonical graph supplied by the caller.
    It never promotes from a model response directly and never infers missing
    semantic identities.
    """

    @staticmethod
    def _binding_matches(candidate: CandidateKnowledge, obligation: VerificationObligation) -> bool:
        params = obligation.parameters
        candidate_id = params.get("candidate_id")
        if candidate_id is not None and str(candidate_id) != candidate.candidate_id:
            return False
        expected = {
            "subject_id": candidate.subject_id,
            "predicate": candidate.predicate,
            "object_id": candidate.object_id,
        }
        supplied = {key: params.get(key) for key in expected if params.get(key) is not None}
        return bool(supplied) and all(str(supplied[key]) == expected[key] for key in supplied)

    def promote(
        self,
        *,
        candidate: CandidateKnowledge,
        obligation: VerificationObligation,
        receipt: VerificationReceipt,
        target_graph: SemanticGraph,
        policy: CandidatePromotionPolicy,
    ) -> CandidatePromotionResult:
        before = graph_fingerprint(target_graph)
        if candidate.state is not VerificationStatus.PROPOSED:
            return CandidatePromotionResult(candidate.candidate_id, False, "candidate_not_proposed")
        if receipt.obligation_id != obligation.obligation_id:
            return CandidatePromotionResult(candidate.candidate_id, False, "receipt_obligation_mismatch")
        if receipt.decision is not VerificationDecision.CONFIRMED:
            return CandidatePromotionResult(candidate.candidate_id, False, "verification_not_confirmed")
        actual_rank = _STATE_RANK.get(receipt.evidence_state, -1)
        required_rank = _STATE_RANK.get(policy.minimum_evidence_state, 999)
        if actual_rank < required_rank:
            return CandidatePromotionResult(candidate.candidate_id, False, "evidence_state_below_policy")
        if policy.allowed_verifier_ids and receipt.verifier_id not in policy.allowed_verifier_ids:
            return CandidatePromotionResult(candidate.candidate_id, False, "verifier_not_allowed")
        if not self._binding_matches(candidate, obligation):
            return CandidatePromotionResult(candidate.candidate_id, False, "candidate_binding_mismatch")
        if not target_graph.has_node(candidate.subject_id) or not target_graph.has_node(candidate.object_id):
            return CandidatePromotionResult(candidate.candidate_id, False, "canonical_endpoint_missing")

        predicate = policy.canonical_predicate or candidate.predicate
        for edge in target_graph.edges:
            if (
                edge.source_id == candidate.subject_id
                and edge.target_id == candidate.object_id
                and edge.relation_type == predicate
            ):
                return CandidatePromotionResult(
                    candidate.candidate_id,
                    False,
                    "canonical_relationship_already_exists",
                    relationship_fingerprint=edge_fingerprint(edge),
                    canonical_predicate=predicate,
                    graph_fingerprint_before=before,
                    graph_fingerprint_after=before,
                )

        edge = SemanticEdge(
            source_id=candidate.subject_id,
            target_id=candidate.object_id,
            relation_type=predicate,
            metadata={
                "promotion": {
                    "candidate_id": candidate.candidate_id,
                    "policy_id": policy.policy_id,
                    "policy_version": policy.version,
                    "receipt_id": receipt.receipt_id,
                    "verifier_id": receipt.verifier_id,
                    "source_analysis_id": receipt.source_analysis_id,
                    "semantic_context_fingerprint": receipt.semantic_context_fingerprint,
                    "evidence_ids": list(receipt.evidence_ids),
                }
            },
        )
        target_graph.add_edge(edge)
        after = graph_fingerprint(target_graph)
        return CandidatePromotionResult(
            candidate_id=candidate.candidate_id,
            promoted=True,
            reason="promoted",
            relationship_fingerprint=edge_fingerprint(edge),
            canonical_predicate=predicate,
            graph_fingerprint_before=before,
            graph_fingerprint_after=after,
            metadata={"receipt_id": receipt.receipt_id},
        )

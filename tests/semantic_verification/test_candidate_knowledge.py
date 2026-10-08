
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.verification import CandidateKnowledge


def test_candidate_knowledge_defaults_to_proposed():
    candidate = CandidateKnowledge.create(
        subject_id="claim:A",
        predicate="POSSIBLY_SUPPORTED_BY",
        object_id="source:B",
    )
    assert candidate.state is VerificationStatus.PROPOSED


def test_candidate_identity_is_deterministic():
    first = CandidateKnowledge.create(subject_id="A", predicate="RELATED_TO", object_id="B")
    second = CandidateKnowledge.create(subject_id="A", predicate="RELATED_TO", object_id="B")
    assert first.candidate_id == second.candidate_id


def test_candidate_rejects_blank_semantic_term():
    try:
        CandidateKnowledge.create(subject_id="A", predicate="", object_id="B")
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("blank candidate predicate should fail")

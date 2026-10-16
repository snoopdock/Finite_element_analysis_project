"""G9.29: neurosymbolic proposal gateway and adjudication controls.

The tests use synthetic model metadata and graph facts. They do not invoke an
LLM and they never execute source programs.
"""
import copy
import hashlib

import pytest

from audit_engine.semantic_audit.ae24 import SCHEMA as C_SCHEMA
from audit_engine.semantic_audit.ae24.contracts import canonical, sha, admit
from audit_engine.semantic_audit.ae26 import snapshot as semantic_snapshot
from audit_engine.semantic_audit.ae27 import (
    SCHEMA, ADJUDICATION_SCHEMA, ProposalError,
    validate_proposal, symbolic_probe, symbolic_probe_set,
    adjudicate, verify_adjudication,
)


def base():
    raw = {"design": b"design-v1", "observed": b"observed-v1"}
    doc = {
        "schema_version": C_SCHEMA, "namespace": "portable/neurosymbolic",
        "sources": [{"id": k, "sha256": hashlib.sha256(v).hexdigest()} for k, v in raw.items()],
        "entities": [
            {"id": "system", "kind": "Component", "source_id": "design"},
            {"id": "reviewer_component", "kind": "Component", "source_id": "design"},
            {"id": "publish", "kind": "Action", "source_id": "design"},
            {"id": "check", "kind": "Check", "source_id": "design"},
        ],
        "assertions": [
            {"id": "forbid", "subject": "system", "predicate": "FORBIDS", "object": "publish",
             "origin": "declared", "source_id": "design"},
            {"id": "observed_action", "subject": "system", "predicate": "PERFORMS", "object": "publish",
             "origin": "observed", "source_id": "observed"},
        ],
    }
    return doc, raw


def candidate(cid="cand1", source_id="observed"):
    return {
        "id": cid, "subject": "system", "predicate": "PERFORMS", "object": "publish",
        "origin": "candidate", "source_id": source_id,
    }


def proposal(doc, raw, candidates=None, links=None, context=None, model_context=True):
    admission = admit(doc, raw)
    semantic = semantic_snapshot(doc, raw)
    context = ["observed_action"] if context is None else context
    model = {
        "adapter_id": "synthetic-neural-adapter",
        "model_family": "test-model",
        "model_version": "1",
    }
    if model_context:
        model["context_sha256"] = sha(canonical({
            "graph_fingerprint": admission.graph_digest,
            "semantic_fingerprint": semantic.semantic_fingerprint,
            "context_occurrences": sorted(set(context)),
        }))
    if candidates is None:
        candidates = [candidate()]
    if links is None:
        links = [{"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"}]
    p = {
        "schema_version": SCHEMA,
        "proposal_id": "proposal-1",
        "base_contract_sha256": admission.contract_digest,
        "base_graph_fingerprint": admission.graph_digest,
        "base_semantic_fingerprint": semantic.semantic_fingerprint,
        "base_hypothesis_fingerprint": semantic.hypothesis_fingerprint,
        "context_occurrences": context,
        "candidate_assertions": candidates,
        "evidence_links": links,
        "model": model,
    }
    p["proposal_sha256"] = sha(canonical(p))
    return p


def test_proposal_schema_is_explicit():
    doc, raw = base()
    p = proposal(doc, raw)
    assert validate_proposal(doc, raw, p)["proposal_sha256"] == p["proposal_sha256"]


def test_model_metadata_is_provenance_not_authority():
    doc, raw = base()
    p = proposal(doc, raw)
    assert validate_proposal(doc, raw, p)["admission"].proposed_count == 0


def test_context_digest_binds_proposal_to_graph_state():
    doc, raw = base()
    p = proposal(doc, raw)
    doc2 = copy.deepcopy(doc)
    doc2["namespace"] = "changed"
    with pytest.raises(ProposalError, match="different contract"):
        validate_proposal(doc2, raw, p)


def test_model_context_digest_mismatch_rejected():
    doc, raw = base()
    p = proposal(doc, raw)
    p["model"]["context_sha256"] = "0" * 64
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="context digest"):
        validate_proposal(doc, raw, p)


def test_candidate_must_remain_candidate_origin():
    doc, raw = base()
    p = proposal(doc, raw)
    p["candidate_assertions"][0]["origin"] = "observed"
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="candidate origin"):
        validate_proposal(doc, raw, p)


def test_candidate_id_collision_rejected():
    doc, raw = base()
    p = proposal(doc, raw, [candidate("observed_action")])
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="collides"):
        validate_proposal(doc, raw, p)


def test_invalid_candidate_relation_rejected_by_ae24():
    doc, raw = base()
    c = candidate()
    c["predicate"] = "DEPENDS_ON"
    p = proposal(doc, raw, [c], links=[])
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="AE-24"):
        validate_proposal(doc, raw, p)


def test_evidence_link_is_many_to_many():
    doc, raw = base()
    doc["assertions"].append({
        "id": "observed_action_2", "subject": "system", "predicate": "PERFORMS",
        "object": "publish", "origin": "observed", "source_id": "observed",
    })
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action_2", "kind": "supports"},
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ]
    p = proposal(doc, raw, candidates, links)
    assert len(validate_proposal(doc, raw, p)["candidate_ids"]) == 2


def test_duplicate_evidence_link_rejected():
    doc, raw = base()
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ]
    p = proposal(doc, raw, links=links)
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="duplicate"):
        validate_proposal(doc, raw, p)


def test_candidate_cannot_be_its_own_evidence():
    doc, raw = base()
    links = [{"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "cand1", "kind": "supports"}]
    p = proposal(doc, raw, links=links)
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError):
        validate_proposal(doc, raw, p)


def test_contradicting_link_is_explicit():
    doc, raw = base()
    links = [{"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "contradicts"}]
    p = proposal(doc, raw, links=links)
    assert validate_proposal(doc, raw, p)["candidate_ids"] == ("cand1",)


def test_candidate_evidence_cannot_support_another_candidate():
    doc, raw = base()
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [{"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "cand2", "kind": "supports"}]
    p = proposal(doc, raw, candidates, links)
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="Candidate evidence"):
        validate_proposal(doc, raw, p)


def test_candidate_evidence_error_precedes_generic_link_validation():
    doc, raw = base()
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "cand2", "kind": "unsupported"}
    ]
    p = proposal(doc, raw, candidates, links)
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="Candidate evidence"):
        validate_proposal(doc, raw, p)


def test_unknown_evidence_occurrence_is_not_misclassified_as_candidate_evidence():
    doc, raw = base()
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "missing", "kind": "supports"}
    ]
    p = proposal(doc, raw, links=links)
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="Invalid or duplicate evidence link"):
        validate_proposal(doc, raw, p)


def test_context_occurrence_must_exist():
    doc, raw = base()
    # Keep valid model metadata so this test isolates the graph-reference
    # invariant rather than the separate mandatory context-digest invariant.
    p = proposal(doc, raw, context=["missing"])
    with pytest.raises(ProposalError, match="Context occurrence"):
        validate_proposal(doc, raw, p)


def test_missing_model_context_digest_is_distinct_from_missing_occurrence():
    doc, raw = base()
    p = proposal(doc, raw, context=["missing"])
    p["model"].pop("context_sha256")
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="model metadata"):
        validate_proposal(doc, raw, p)


def test_proposal_digest_rejects_tampering():
    doc, raw = base()
    p = proposal(doc, raw)
    p["proposal_id"] = "tampered"
    with pytest.raises(ProposalError, match="digest"):
        validate_proposal(doc, raw, p)


def test_symbolic_probe_conflict_is_counterfactual():
    doc, raw = base()
    result = symbolic_probe(doc, raw, candidate())
    assert result["probe_status"] == "symbolically_conflicted"
    assert result["authority"]["counterfactual_only"]
    assert not result["authority"]["candidate_promoted"]


def test_symbolic_probe_can_find_no_conflict():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    result = symbolic_probe(doc, raw, candidate())
    assert result["probe_status"] == "not_conflicted_under_admitted_rules"


def test_symbolic_probe_does_not_mutate_contract():
    doc, raw = base()
    frozen = copy.deepcopy(doc)
    symbolic_probe(doc, raw, candidate())
    assert doc == frozen


def test_adjudication_acceptance_is_not_promotion():
    doc, raw = base()
    # Remove the prohibition so the candidate is not symbolically conflicted.
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a",
        "candidate_occurrence_ids": ["cand1"], "decision": "accept",
        "evidence_occurrence_ids": ["observed_action"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["disposition"] == "supported_candidate_requires_explicit_admission"
    assert out["authority"]["candidate_promoted_to_authoritative_fact"] is False


def test_rejected_candidate_is_not_promoted():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a",
        "candidate_occurrence_ids": ["cand1"], "decision": "reject",
        "evidence_occurrence_ids": ["observed_action"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["disposition"] == "rejected_candidate"


def test_deferred_review_remains_unresolved():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a",
        "candidate_occurrence_ids": ["cand1"], "decision": "defer",
        "evidence_occurrence_ids": [],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["disposition"] == "unresolved_candidate"


def test_review_conflict_is_explicit():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw)
    reviews = [
        {"id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
         "decision": "accept", "evidence_occurrence_ids": ["observed_action"]},
        {"id": "r2", "reviewer_id": "reviewer-b", "candidate_occurrence_ids": ["cand1"],
         "decision": "reject", "evidence_occurrence_ids": ["observed_action"]},
    ]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["review_status"] == "review_conflict"
    assert out["candidates"][0]["disposition"] == "unresolved_review_conflict"


def test_symbolic_conflict_overrides_acceptance():
    doc, raw = base()
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a",
        "candidate_occurrence_ids": ["cand1"], "decision": "accept",
        "evidence_occurrence_ids": ["observed_action"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["disposition"] == "symbolically_conflicted_candidate"


def test_contradicting_evidence_prevents_supported_disposition():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw, links=[
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "contradicts"},
    ])
    # Duplicate pair is intentionally forbidden; construct a second evidence occurrence.
    doc["assertions"].append({
        "id": "contradictory_obs", "subject": "reviewer_component", "predicate": "PERFORMS",
        "object": "publish", "origin": "observed", "source_id": "observed",
    })
    p = proposal(doc, raw, links=[
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "contradictory_obs", "kind": "contradicts"},
    ])
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
        "decision": "accept", "evidence_occurrence_ids": ["observed_action", "contradictory_obs"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["disposition"] == "unresolved_candidate"


def test_review_evidence_can_expand_beyond_model_links():
    doc, raw = base()
    doc["assertions"].append({
        "id": "review_obs", "subject": "reviewer_component", "predicate": "PERFORMS",
        "object": "publish", "origin": "observed", "source_id": "observed",
    })
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw, links=[
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ])
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
        "decision": "accept", "evidence_occurrence_ids": ["review_obs"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["review_status"] == "accepted"


def test_same_evidence_can_support_multiple_candidates():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ]
    p = proposal(doc, raw, candidates, links)
    reviews = [
        {"id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1", "cand2"],
         "decision": "accept", "evidence_occurrence_ids": ["observed_action"]},
    ]
    out = adjudicate(doc, raw, p, reviews)
    assert len(out["candidates"]) == 2


def test_one_review_event_can_cover_multiple_candidates():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ]
    p = proposal(doc, raw, candidates, links)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a",
        "candidate_occurrence_ids": ["cand1", "cand2"], "decision": "accept",
        "evidence_occurrence_ids": ["observed_action"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert {x["review_status"] for x in out["candidates"]} == {"accepted"}


def test_same_reviewer_can_issue_separate_review_events():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ]
    p = proposal(doc, raw, candidates, links)
    reviews = [
        {"id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
         "decision": "accept", "evidence_occurrence_ids": ["observed_action"]},
        {"id": "r2", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand2"],
         "decision": "defer", "evidence_occurrence_ids": []},
    ]
    out = adjudicate(doc, raw, p, reviews)
    assert [x["review_status"] for x in out["candidates"]] == ["accepted", "deferred"]


def test_unreviewed_candidate_is_unresolved():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw)
    out = adjudicate(doc, raw, p, [])
    assert out["candidates"][0]["review_status"] == "unreviewed"
    assert out["candidates"][0]["disposition"] == "unresolved_candidate"


def test_adjudication_exact_replay():
    doc, raw = base()
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a",
        "candidate_occurrence_ids": ["cand1"], "decision": "accept",
        "evidence_occurrence_ids": ["observed_action"],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert verify_adjudication(doc, raw, p, reviews, out)


def test_adjudication_tampering_rejected():
    doc, raw = base()
    p = proposal(doc, raw)
    out = adjudicate(doc, raw, p, [])
    out["authority"]["candidate_promoted_to_authoritative_fact"] = True
    with pytest.raises(ProposalError, match="replay"):
        verify_adjudication(doc, raw, p, [], out)


def test_source_tampering_invalidates_adjudication():
    doc, raw = base()
    p = proposal(doc, raw)
    out = adjudicate(doc, raw, p, [])
    raw["observed"] = b"changed"
    with pytest.raises(ValueError):
        verify_adjudication(doc, raw, p, [], out)


def test_no_automatic_graph_mutation():
    doc, raw = base()
    original = copy.deepcopy(doc)
    p = proposal(doc, raw)
    adjudicate(doc, raw, p, [])
    assert doc == original


def test_reviewer_identity_does_not_establish_independence():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw)
    reviews = [
        {"id": "r1", "reviewer_id": "same", "candidate_occurrence_ids": ["cand1"],
         "decision": "accept", "evidence_occurrence_ids": ["observed_action"]},
        {"id": "r2", "reviewer_id": "same", "candidate_occurrence_ids": ["cand1"],
         "decision": "accept", "evidence_occurrence_ids": ["observed_action"]},
    ]
    out = adjudicate(doc, raw, p, reviews)
    assert out["authority"]["reviewer_independence_established"] is False


def test_missing_review_evidence_is_allowed_but_cannot_create_support():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    p = proposal(doc, raw, links=[])
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
        "decision": "accept", "evidence_occurrence_ids": [],
    }]
    out = adjudicate(doc, raw, p, reviews)
    assert out["candidates"][0]["disposition"] == "unresolved_candidate"


def test_invalid_review_candidate_rejected():
    doc, raw = base()
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["missing"],
        "decision": "accept", "evidence_occurrence_ids": [],
    }]
    with pytest.raises(ProposalError, match="unknown candidate"):
        adjudicate(doc, raw, p, reviews)


def test_invalid_review_evidence_rejected():
    doc, raw = base()
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
        "decision": "accept", "evidence_occurrence_ids": ["missing"],
    }]
    with pytest.raises(ProposalError, match="unknown evidence"):
        adjudicate(doc, raw, p, reviews)


def test_unsupported_review_decision_rejected():
    doc, raw = base()
    p = proposal(doc, raw)
    reviews = [{
        "id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
        "decision": "promote", "evidence_occurrence_ids": [],
    }]
    with pytest.raises(ProposalError, match="decision"):
        adjudicate(doc, raw, p, reviews)


def test_candidate_count_limit_fails_closed():
    doc, raw = base()
    candidates = [candidate(f"c{i}") for i in range(201)]
    links = [{"candidate_occurrence_id": c["id"], "evidence_occurrence_id": "observed_action", "kind": "supports"} for c in candidates]
    p = proposal(doc, raw, candidates, links)
    with pytest.raises(ProposalError, match="candidate set"):
        validate_proposal(doc, raw, p)


def test_link_limit_fails_closed():
    doc, raw = base()
    # Reuse distinct candidates; 200 candidates cannot exceed link limit here,
    # so this check targets the envelope rather than symbolic evaluation.
    p = proposal(doc, raw)
    p["evidence_links"] = [{"candidate_occurrence_id": "cand1",
                            "evidence_occurrence_id": "observed_action",
                            "kind": "supports"}] * 2001
    p["proposal_sha256"] = sha(canonical({k:v for k,v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="evidence-link"):
        validate_proposal(doc, raw, p)


def test_model_context_digest_is_required():
    doc, raw = base()
    p = proposal(doc, raw, model_context=False)
    with pytest.raises(ProposalError, match="model metadata"):
        validate_proposal(doc, raw, p)


def test_context_cannot_use_prior_candidate_hypothesis():
    doc, raw = base()
    doc["assertions"].append(candidate("prior_candidate"))
    p = proposal(doc, raw, context=["prior_candidate"])
    with pytest.raises(ProposalError, match="declared or observed"):
        validate_proposal(doc, raw, p)


def test_semantic_state_binding_is_required():
    doc, raw = base()
    p = proposal(doc, raw)
    p["base_semantic_fingerprint"] = "0" * 64
    p["proposal_sha256"] = sha(canonical({k: v for k, v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="semantic state"):
        validate_proposal(doc, raw, p)


def test_hypothesis_state_binding_is_required():
    doc, raw = base()
    p = proposal(doc, raw)
    p["base_hypothesis_fingerprint"] = "0" * 64
    p["proposal_sha256"] = sha(canonical({k: v for k, v in p.items() if k != "proposal_sha256"}))
    with pytest.raises(ProposalError, match="hypothesis state"):
        validate_proposal(doc, raw, p)


def interaction_base():
    raw = {"design": b"design-interaction", "observed": b"observed-interaction"}
    doc = {
        "schema_version": C_SCHEMA,
        "namespace": "portable/neurosymbolic/joint",
        "sources": [
            {"id": key, "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in raw.items()
        ],
        "entities": [
            {"id": "a", "kind": "Component", "source_id": "design"},
            {"id": "b", "kind": "Component", "source_id": "design"},
        ],
        "assertions": [],
        "policies": [
            {"id": "acyclic", "kind": "acyclic_dependencies", "source_id": "design"},
        ],
    }
    return doc, raw


def dependency_candidate(cid, subject, object_):
    return {
        "id": cid,
        "subject": subject,
        "predicate": "DEPENDS_ON",
        "object": object_,
        "origin": "candidate",
        "source_id": "design",
    }


def interaction_proposal(doc, raw, candidates):
    # Add one authoritative context fact only for proposal state binding.
    doc = copy.deepcopy(doc)
    doc["entities"].append({"id": "observer", "kind": "Component", "source_id": "design"})
    doc["entities"].append({"id": "action", "kind": "Action", "source_id": "design"})
    doc["assertions"].append({
        "id": "context_obs",
        "subject": "observer",
        "predicate": "PERFORMS",
        "object": "action",
        "origin": "observed",
        "source_id": "observed",
    })
    return proposal(doc, raw, candidates=candidates, links=[],
                    context=["context_obs"]), doc


def test_joint_probe_catches_collective_dependency_cycle():
    doc, raw = interaction_base()
    candidates = [
        dependency_candidate("cand-a", "a", "b"),
        dependency_candidate("cand-b", "b", "a"),
    ]
    result = symbolic_probe_set(doc, raw, candidates)
    assert result["set_status"] == "symbolically_conflicted"
    assert {x["probe_status"] for x in result["candidate_results"]} == {"symbolically_conflicted"}
    assert result["authority"]["joint_candidate_interactions_evaluated"] is True


def test_individual_probes_can_miss_collective_dependency_cycle():
    doc, raw = interaction_base()
    first = dependency_candidate("cand-a", "a", "b")
    second = dependency_candidate("cand-b", "b", "a")
    assert symbolic_probe(doc, raw, first)["probe_status"] == "not_conflicted_under_admitted_rules"
    assert symbolic_probe(doc, raw, second)["probe_status"] == "not_conflicted_under_admitted_rules"
    assert symbolic_probe_set(doc, raw, [first, second])["set_status"] == "symbolically_conflicted"


def test_adjudication_uses_joint_candidate_probe():
    doc, raw = interaction_base()
    candidates = [
        dependency_candidate("cand-a", "a", "b"),
        dependency_candidate("cand-b", "b", "a"),
    ]
    p, doc = interaction_proposal(doc, raw, candidates)
    reviews = [
        {"id": "r-a", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand-a"],
         "decision": "accept", "evidence_occurrence_ids": ["context_obs"]},
        {"id": "r-b", "reviewer_id": "reviewer-b", "candidate_occurrence_ids": ["cand-b"],
         "decision": "accept", "evidence_occurrence_ids": ["context_obs"]},
    ]
    out = adjudicate(doc, raw, p, reviews)
    assert out["joint_probe_status"] == "symbolically_conflicted"
    assert {x["disposition"] for x in out["candidates"]} == {"symbolically_conflicted_candidate"}


def test_review_digest_is_order_independent():
    doc, raw = base()
    doc["assertions"] = [x for x in doc["assertions"] if x["id"] != "forbid"]
    candidates = [candidate("cand1"), candidate("cand2")]
    links = [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ]
    p = proposal(doc, raw, candidates, links)
    reviews = [
        {"id": "r1", "reviewer_id": "reviewer-a", "candidate_occurrence_ids": ["cand1"],
         "decision": "accept", "evidence_occurrence_ids": ["observed_action"]},
        {"id": "r2", "reviewer_id": "reviewer-b", "candidate_occurrence_ids": ["cand2"],
         "decision": "defer", "evidence_occurrence_ids": []},
    ]
    one = adjudicate(doc, raw, p, reviews)
    two = adjudicate(doc, raw, p, list(reversed(reviews)))
    assert one == two
    assert one["review_digest"] == two["review_digest"]


def test_joint_probe_does_not_mutate_contract():
    doc, raw = interaction_base()
    candidates = [
        dependency_candidate("cand-a", "a", "b"),
        dependency_candidate("cand-b", "b", "a"),
    ]
    frozen = copy.deepcopy(doc)
    symbolic_probe_set(doc, raw, candidates)
    assert doc == frozen

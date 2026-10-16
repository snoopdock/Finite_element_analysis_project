"""G9.30 / AE-28 deterministic neural/LLM interpretation boundary tests.

These tests do not invoke an LLM, network, subprocess, repository source, or
automatic writeback. They exercise the exact intake/replay boundary that a
future provider adapter must satisfy.
"""
import copy
import hashlib
import json

import pytest

from audit_engine.semantic_audit.ae24 import SCHEMA as C_SCHEMA
from audit_engine.semantic_audit.ae24.contracts import admit, canonical, sha
from audit_engine.semantic_audit.ae26 import snapshot as semantic_snapshot
from audit_engine.semantic_audit.ae28 import (
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    INTERPRETATION_SCHEMA,
    NeuralInterpretationError,
    make_request,
    verify_request,
    ingest_model_response,
    verify_interpretation,
    response_from_canonical_bytes,
)


def base():
    raw = {
        "design": b"design-v1",
        "observed": b"observed-v1",
    }
    doc = {
        "schema_version": C_SCHEMA,
        "namespace": "portable/neural-audit",
        "sources": [
            {"id": key, "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in raw.items()
        ],
        "entities": [
            {"id": "system", "kind": "Component", "source_id": "design"},
            {"id": "publish", "kind": "Action", "source_id": "design"},
        ],
        "assertions": [
            {
                "id": "forbid",
                "subject": "system",
                "predicate": "FORBIDS",
                "object": "publish",
                "origin": "declared",
                "source_id": "design",
            },
            {
                "id": "observed_action",
                "subject": "system",
                "predicate": "PERFORMS",
                "object": "publish",
                "origin": "observed",
                "source_id": "observed",
            },
        ],
    }
    return doc, raw


def task_digest():
    return "1" * 64


def manifest():
    return [
        {"id": "input-design", "sha256": "2" * 64},
        {"id": "input-context", "sha256": "3" * 64},
    ]


def request(doc, raw, context=None, manifest_value=None):
    return make_request(
        doc,
        raw,
        request_id="request-1",
        context_occurrences=["observed_action"] if context is None else context,
        task_digest=task_digest(),
        input_manifest=manifest() if manifest_value is None else manifest_value,
    )


def response(doc, raw, req=None, candidates=None, links=None):
    req = request(doc, raw) if req is None else req
    admission = admit(doc, raw)
    semantic = semantic_snapshot(doc, raw)
    context_digest = sha(
        canonical(
            {
                "graph_fingerprint": admission.graph_digest,
                "semantic_fingerprint": semantic.semantic_fingerprint,
                "context_occurrences": sorted(req["context_occurrences"]),
            }
        )
    )
    raw_model_output = b'{"external":"model-response"}'
    response = {
        "schema_version": RESPONSE_SCHEMA,
        "request_sha256": req["request_sha256"],
        "proposal_id": "proposal-1",
        "model": {
            "adapter_id": "reference-adapter",
            "model_family": "reference-model",
            "model_version": "1",
            "context_sha256": context_digest,
        },
        "model_trace": {
            "adapter_id": "reference-adapter",
            "model_family": "reference-model",
            "model_version": "1",
            "raw_output_sha256": sha(raw_model_output),
            "generation_config_sha256": "4" * 64,
        },
        "candidate_assertions": (
            [
                {
                    "id": "cand1",
                    "subject": "system",
                    "predicate": "PERFORMS",
                    "object": "publish",
                    "origin": "candidate",
                    "source_id": "observed",
                }
            ]
            if candidates is None
            else candidates
        ),
        "evidence_links": (
            [
                {
                    "candidate_occurrence_id": "cand1",
                    "evidence_occurrence_id": "observed_action",
                    "kind": "supports",
                }
            ]
            if links is None
            else links
        ),
    }
    response["response_sha256"] = sha(canonical(response))
    return raw_model_output, response


def test_request_is_source_and_semantic_state_bound():
    doc, raw = base()
    req = request(doc, raw)
    assert req["schema_version"] == REQUEST_SCHEMA
    assert req["base_contract_sha256"] == admit(doc, raw).contract_digest
    assert req["base_semantic_fingerprint"] == semantic_snapshot(doc, raw).semantic_fingerprint
    assert verify_request(doc, raw, req) == req


def test_request_records_prompt_task_only_as_digest():
    doc, raw = base()
    req = request(doc, raw)
    assert "prompt" not in req
    assert req["task_digest"] == task_digest()


def test_request_context_is_canonicalized():
    doc, raw = base()
    req = request(
        doc,
        raw,
        manifest_value=list(reversed(manifest())),
    )
    assert req["input_manifest"] == sorted(manifest(), key=lambda x: x["id"])


def test_request_rejects_missing_context():
    doc, raw = base()
    with pytest.raises(NeuralInterpretationError, match="not in the admitted graph"):
        request(doc, raw, context=["missing"])


def test_request_rejects_candidate_context():
    doc, raw = base()
    doc["assertions"].append(
        {
            "id": "candidate_context",
            "subject": "system",
            "predicate": "PERFORMS",
            "object": "publish",
            "origin": "candidate",
            "source_id": "observed",
        }
    )
    with pytest.raises(NeuralInterpretationError, match="declared or observed"):
        request(doc, raw, context=["candidate_context"])


def test_request_rejects_non_digest_task():
    doc, raw = base()
    with pytest.raises(NeuralInterpretationError, match="task digest"):
        make_request(
            doc,
            raw,
            request_id="request-1",
            context_occurrences=["observed_action"],
            task_digest="not-a-digest",
            input_manifest=manifest(),
        )


def test_request_rejects_duplicate_manifest_ids():
    doc, raw = base()
    duplicate = [manifest()[0], manifest()[0]]
    with pytest.raises(NeuralInterpretationError, match="Duplicate input artifact"):
        request(doc, raw, manifest_value=duplicate)


def test_request_detects_contract_drift():
    doc, raw = base()
    req = request(doc, raw)
    changed = copy.deepcopy(doc)
    changed["namespace"] = "changed"
    with pytest.raises(NeuralInterpretationError, match="current source/semantic state"):
        verify_request(changed, raw, req)


def test_response_is_bound_to_request():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["request_sha256"] = "5" * 64
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="different request"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_raw_model_output_digest_is_verified():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    with pytest.raises(NeuralInterpretationError, match="Raw model output digest"):
        ingest_model_response(doc, raw, req, b"tampered", resp)


def test_response_digest_is_verified():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["proposal_id"] = "changed"
    with pytest.raises(NeuralInterpretationError, match="response digest"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_model_trace_and_model_metadata_must_agree():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"]["model_version"] = "2"
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="disagrees"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_generation_configuration_digest_is_required():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model_trace"].pop("generation_config_sha256")
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model trace"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_model_context_must_match_request():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"]["context_sha256"] = "6" * 64
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="context digest"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_ae27_proposal_is_created_with_candidate_only_authority():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    assert out["schema_version"] == INTERPRETATION_SCHEMA
    assert out["proposal"]["schema_version"].startswith("ae27/")
    assert out["authority"]["candidate_only"] is True
    assert out["authority"]["automatic_graph_mutation_permitted"] is False
    assert out["authority"]["candidate_promoted_to_authoritative_fact"] is False


def test_ingest_does_not_mutate_contract():
    doc, raw = base()
    frozen = copy.deepcopy(doc)
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    ingest_model_response(doc, raw, req, raw_model, resp)
    assert doc == frozen


def test_candidate_order_is_normalized_before_ae27_proposal_creation():
    doc, raw = base()
    req = request(doc, raw)
    c1 = {
        "id": "cand1",
        "subject": "system",
        "predicate": "PERFORMS",
        "object": "publish",
        "origin": "candidate",
        "source_id": "observed",
    }
    c2 = {
        "id": "cand2",
        "subject": "system",
        "predicate": "PERFORMS",
        "object": "publish",
        "origin": "candidate",
        "source_id": "observed",
    }
    raw1, r1 = response(doc, raw, req, [c1, c2], [
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ])
    raw2, r2 = response(doc, raw, req, [c2, c1], [
        {"candidate_occurrence_id": "cand2", "evidence_occurrence_id": "observed_action", "kind": "supports"},
        {"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "observed_action", "kind": "supports"},
    ])
    out1 = ingest_model_response(doc, raw, req, raw1, r1)
    out2 = ingest_model_response(doc, raw, req, raw2, r2)
    assert out1["proposal"]["proposal_sha256"] == out2["proposal"]["proposal_sha256"]


def test_unknown_evidence_remains_ae27_error():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(
        doc,
        raw,
        req,
        links=[
            {
                "candidate_occurrence_id": "cand1",
                "evidence_occurrence_id": "missing",
                "kind": "supports",
            }
        ],
    )
    with pytest.raises(NeuralInterpretationError, match="AE-27 rejected"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_candidate_as_evidence_remains_rejected():
    doc, raw = base()
    req = request(doc, raw)
    candidates = [
        {
            "id": "cand1",
            "subject": "system",
            "predicate": "PERFORMS",
            "object": "publish",
            "origin": "candidate",
            "source_id": "observed",
        },
        {
            "id": "cand2",
            "subject": "system",
            "predicate": "PERFORMS",
            "object": "publish",
            "origin": "candidate",
            "source_id": "observed",
        },
    ]
    raw_model, resp = response(
        doc,
        raw,
        req,
        candidates,
        [{"candidate_occurrence_id": "cand1", "evidence_occurrence_id": "cand2", "kind": "supports"}],
    )
    with pytest.raises(NeuralInterpretationError, match="Candidate evidence"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_model_cannot_self_declare_authority():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["authority"] = {"verified": True}
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model response envelope"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_model_confidence_is_not_an_accepted_model_metadata_field():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"]["confidence"] = 0.99
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model metadata"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_unknown_model_metadata_field_is_classified_as_metadata_error():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"]["provider_confidence"] = 0.99
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model metadata"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_missing_model_metadata_field_is_classified_as_metadata_error():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"].pop("model_version")
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model metadata"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_model_metadata_value_is_validated_at_ae28_boundary():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"]["adapter_id"] = ""
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model metadata value"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_model_context_digest_format_is_validated_at_ae28_boundary():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model"]["context_sha256"] = "not-a-digest"
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model context digest"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_canonical_json_response_parser_is_strict():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    encoded = canonical(resp)
    assert response_from_canonical_bytes(encoded)["response_sha256"] == resp["response_sha256"]
    with pytest.raises(NeuralInterpretationError, match="canonical JSON"):
        response_from_canonical_bytes(json.dumps(resp).encode())


def test_exact_interpretation_replay_passes():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    assert verify_interpretation(doc, raw, req, raw_model, resp, out)


def test_interpretation_tampering_is_detected():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    tampered = copy.deepcopy(out)
    tampered["proposal"]["proposal_id"] = "tampered"
    with pytest.raises(NeuralInterpretationError, match="exact source replay"):
        verify_interpretation(doc, raw, req, raw_model, resp, tampered)


def test_semantic_state_drift_invalidates_interpretation():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    changed = copy.deepcopy(doc)
    changed["assertions"].append(
        {
            "id": "new_observation",
            "subject": "system",
            "predicate": "PERFORMS",
            "object": "publish",
            "origin": "observed",
            "source_id": "observed",
        }
    )
    with pytest.raises(NeuralInterpretationError):
        verify_interpretation(changed, raw, req, raw_model, resp, out)


def test_hypothesis_fingerprint_is_bound():
    doc, raw = base()
    doc["assertions"].append(
        {
            "id": "prior_candidate",
            "subject": "system",
            "predicate": "PERFORMS",
            "object": "publish",
            "origin": "candidate",
            "source_id": "observed",
        }
    )
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    changed = copy.deepcopy(doc)
    changed["assertions"][-1]["id"] = "prior_candidate_changed"
    with pytest.raises(NeuralInterpretationError):
        verify_interpretation(changed, raw, req, raw_model, resp, out)


def test_input_manifest_digest_is_recorded_but_not_authority():
    doc, raw = base()
    req = request(doc, raw)
    assert req["input_manifest"]
    assert "authority" not in req


def test_empty_raw_output_is_allowed_but_still_hashed():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    raw_model = b""
    resp["model_trace"]["raw_output_sha256"] = sha(raw_model)
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    assert out["model_trace"]["raw_output_sha256"] == sha(b"")


def test_oversized_raw_output_is_rejected():
    doc, raw = base()
    req = request(doc, raw)
    _, resp = response(doc, raw, req)
    with pytest.raises(NeuralInterpretationError, match="bounded bytes"):
        ingest_model_response(doc, raw, req, b"x" * 4_000_001, resp)


def test_response_requires_candidate_set():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["candidate_assertions"] = []
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="must contain candidates"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_response_rejects_unknown_top_level_field():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["unexpected"] = True
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model response envelope"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_response_model_trace_cannot_claim_verified_truth():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    resp["model_trace"]["truth_verified"] = True
    resp["response_sha256"] = sha(canonical({k: v for k, v in resp.items() if k != "response_sha256"}))
    with pytest.raises(NeuralInterpretationError, match="Invalid model trace"):
        ingest_model_response(doc, raw, req, raw_model, resp)


def test_request_semantic_vocabulary_is_recorded():
    doc, raw = base()
    req = request(doc, raw)
    assert req["vocabulary_digest"] == semantic_snapshot(doc, raw).vocabulary_digest


def test_response_normalization_preserves_raw_output_provenance():
    doc, raw = base()
    req = request(doc, raw)
    raw_model, resp = response(doc, raw, req)
    out = ingest_model_response(doc, raw, req, raw_model, resp)
    assert out["model_trace"]["raw_output_sha256"] == sha(raw_model)
    assert out["response_sha256"] == resp["response_sha256"]


def test_future_prompt_changes_can_be_detected_without_changing_schema():
    doc, raw = base()
    req1 = request(doc, raw)
    req2 = make_request(
        doc,
        raw,
        request_id="request-2",
        context_occurrences=["observed_action"],
        task_digest="7" * 64,
        input_manifest=manifest(),
    )
    assert req1["task_digest"] != req2["task_digest"]
    assert req1["base_semantic_fingerprint"] == req2["base_semantic_fingerprint"]

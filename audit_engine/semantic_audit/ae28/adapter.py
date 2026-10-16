"""AE-28: provider-neutral neural/LLM interpretation intake.

AE-28 does not invoke a model. It consumes a bounded raw model response and a
strictly validated, structured interpretation produced by an external adapter.
It binds that interpretation to the exact repository contract/semantic state
and converts it into the AE-27 candidate-only proposal protocol.

The runtime prompt/task formulation is intentionally represented only by a
digest in this milestone; prompt design is a later integration decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
import re
from typing import Any, Mapping

from audit_engine.semantic_audit.ae24.contracts import (
    admit,
    canonical,
    sha,
    ContractError,
    MAX_SOURCE_BYTES,
)
from audit_engine.semantic_audit.ae26.semantics import snapshot as semantic_snapshot
from audit_engine.semantic_audit.ae27.bridge import (
    validate_proposal,
    ProposalError,
    SCHEMA as AE27_SCHEMA,
)

REQUEST_SCHEMA = "ae28/neural-request/v1"
RESPONSE_SCHEMA = "ae28/neural-model-response/v1"
INTERPRETATION_SCHEMA = "ae28/neural-interpretation/v1"

MAX_CONTEXT = 2000
MAX_INPUT_MANIFEST = 2000
MAX_RAW_OUTPUT_BYTES = 4_000_000
MAX_RESPONSE_BYTES = 4_000_000
MAX_TASK_DIGESTS = 64
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
GRAPH_FINGERPRINT = re.compile(r"^graph:[0-9a-f]{32}$")


class NeuralInterpretationError(ValueError):
    """Invalid, stale, ungrounded, or non-replayable neural interpretation."""


@dataclass(frozen=True)
class NeuralRequest:
    payload: dict[str, Any]

    @property
    def request_sha256(self) -> str:
        return self.payload["request_sha256"]


def _sha_json(value: Any) -> str:
    return sha(canonical(value))


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise NeuralInterpretationError(f"Invalid {label}")
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise NeuralInterpretationError(f"Invalid {label}")
    return value


def _body_without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    body = copy.deepcopy(value)
    body.pop(field, None)
    return body


def _context_digest(
    graph_fingerprint: str,
    semantic_fingerprint: str,
    context_occurrences: list[str],
) -> str:
    return _sha_json(
        {
            "graph_fingerprint": graph_fingerprint,
            "semantic_fingerprint": semantic_fingerprint,
            "context_occurrences": sorted(set(context_occurrences)),
        }
    )


def _validate_manifest(manifest: Any) -> list[dict[str, str]]:
    if not isinstance(manifest, list) or len(manifest) > MAX_INPUT_MANIFEST:
        raise NeuralInterpretationError("Invalid input manifest")
    normalized = []
    seen = set()
    for item in manifest:
        if not isinstance(item, dict) or set(item) != {"id", "sha256"}:
            raise NeuralInterpretationError("Invalid input manifest entry")
        ident = _safe_id(item["id"], "input artifact identity")
        digest = _require_digest(item["sha256"], "input artifact digest")
        if ident in seen:
            raise NeuralInterpretationError("Duplicate input artifact identity")
        seen.add(ident)
        normalized.append({"id": ident, "sha256": digest})
    return sorted(normalized, key=lambda item: item["id"])


def _validate_request_shape(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise NeuralInterpretationError("Request must be an object")
    allowed = {
        "schema_version",
        "request_id",
        "base_contract_sha256",
        "base_graph_fingerprint",
        "base_semantic_fingerprint",
        "base_hypothesis_fingerprint",
        "vocabulary_digest",
        "context_occurrences",
        "task_digest",
        "input_manifest",
        "request_sha256",
    }
    required = allowed - {"request_sha256"}
    if set(request) - allowed or not required <= set(request):
        raise NeuralInterpretationError("Invalid request envelope")
    if request["schema_version"] != REQUEST_SCHEMA:
        raise NeuralInterpretationError("Unsupported request schema")
    _safe_id(request["request_id"], "request identity")
    for field in (
        "base_contract_sha256",
        "base_semantic_fingerprint",
        "base_hypothesis_fingerprint",
        "vocabulary_digest",
        "task_digest",
    ):
        _require_digest(request[field], field)
    if not isinstance(request["base_graph_fingerprint"], str) or not GRAPH_FINGERPRINT.fullmatch(
        request["base_graph_fingerprint"]
    ):
        raise NeuralInterpretationError("Invalid base_graph_fingerprint")
    context = request["context_occurrences"]
    if (
        not isinstance(context, list)
        or not context
        or len(context) > MAX_CONTEXT
        or len(context) != len(set(context))
        or any(not isinstance(x, str) or not SAFE_ID.fullmatch(x) for x in context)
    ):
        raise NeuralInterpretationError("Invalid request context")
    _validate_manifest(request["input_manifest"])
    if "request_sha256" in request:
        _require_digest(request["request_sha256"], "request digest")
    return request


def make_request(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    *,
    request_id: str,
    context_occurrences: list[str],
    task_digest: str,
    input_manifest: list[dict[str, str]],
) -> dict[str, Any]:
    """Create a deterministic, source-bound request envelope.

    ``task_digest`` is the digest of the caller's task/prompt formulation. AE-28
    deliberately does not prescribe or persist a prompt template.
    """
    try:
        admission = admit(contract, sources)
        semantic = semantic_snapshot(contract, sources)
    except (ContractError, ValueError) as exc:
        raise NeuralInterpretationError(f"Unable to bind request to contract: {exc}") from exc

    _safe_id(request_id, "request identity")
    _require_digest(task_digest, "task digest")
    if (
        not isinstance(context_occurrences, list)
        or not context_occurrences
        or len(context_occurrences) > MAX_CONTEXT
        or len(context_occurrences) != len(set(context_occurrences))
    ):
        raise NeuralInterpretationError("Invalid request context")
    base = {row["id"]: row for row in contract["assertions"]}
    for occurrence in context_occurrences:
        _safe_id(occurrence, "context occurrence identity")
        if occurrence not in base:
            raise NeuralInterpretationError("Request context occurrence is not in the admitted graph")
        if base[occurrence]["origin"] not in {"declared", "observed"}:
            raise NeuralInterpretationError("Request context occurrence must be declared or observed")

    manifest = _validate_manifest(input_manifest)
    body = {
        "schema_version": REQUEST_SCHEMA,
        "request_id": request_id,
        "base_contract_sha256": admission.contract_digest,
        "base_graph_fingerprint": admission.graph_digest,
        "base_semantic_fingerprint": semantic.semantic_fingerprint,
        "base_hypothesis_fingerprint": semantic.hypothesis_fingerprint,
        "vocabulary_digest": semantic.vocabulary_digest,
        "context_occurrences": sorted(context_occurrences),
        "task_digest": task_digest,
        "input_manifest": manifest,
    }
    body["request_sha256"] = _sha_json(body)
    return body


def verify_request(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Replay the request against current source/semantic state."""
    request = _validate_request_shape(request)
    expected = make_request(
        contract,
        sources,
        request_id=request["request_id"],
        context_occurrences=list(request["context_occurrences"]),
        task_digest=request["task_digest"],
        input_manifest=list(request["input_manifest"]),
    )
    if expected != request:
        raise NeuralInterpretationError("Request does not match current source/semantic state")
    return expected


def _validate_model_trace(trace: Any, raw_output: bytes) -> dict[str, str]:
    if not isinstance(trace, dict):
        raise NeuralInterpretationError("Model trace is required")
    allowed = {
        "adapter_id",
        "model_family",
        "model_version",
        "raw_output_sha256",
        "generation_config_sha256",
    }
    required = allowed
    if set(trace) != required:
        raise NeuralInterpretationError("Invalid model trace")
    normalized = {}
    for key in ("adapter_id", "model_family", "model_version"):
        value = trace[key]
        if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
            raise NeuralInterpretationError("Invalid model trace value")
        normalized[key] = value
    raw_digest = _require_digest(trace["raw_output_sha256"], "raw model output digest")
    if sha(raw_output) != raw_digest:
        raise NeuralInterpretationError("Raw model output digest mismatch")
    normalized["raw_output_sha256"] = raw_digest
    normalized["generation_config_sha256"] = _require_digest(
        trace["generation_config_sha256"], "generation configuration digest"
    )
    return normalized


def _validate_response_shape(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise NeuralInterpretationError("Model response must be an object")
    allowed = {
        "schema_version",
        "request_sha256",
        "proposal_id",
        "model",
        "model_trace",
        "candidate_assertions",
        "evidence_links",
        "response_sha256",
    }
    required = allowed - {"response_sha256"}
    if set(response) - allowed or not required <= set(response):
        raise NeuralInterpretationError("Invalid model response envelope")
    if response["schema_version"] != RESPONSE_SCHEMA:
        raise NeuralInterpretationError("Unsupported model response schema")
    _require_digest(response["request_sha256"], "response request digest")
    _safe_id(response["proposal_id"], "proposal identity")
    if not isinstance(response["candidate_assertions"], list) or not response["candidate_assertions"]:
        raise NeuralInterpretationError("Model response must contain candidates")
    if not isinstance(response["evidence_links"], list):
        raise NeuralInterpretationError("Model response evidence links must be a list")
    if "response_sha256" in response:
        _require_digest(response["response_sha256"], "response digest")
    return response


def _canonicalize_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(not isinstance(item, dict) for item in candidates):
        raise NeuralInterpretationError("Candidate assertions must be objects")
    try:
        return sorted(copy.deepcopy(candidates), key=lambda item: item["id"])
    except KeyError as exc:
        raise NeuralInterpretationError("Candidate assertion identity is required") from exc


def _canonicalize_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(not isinstance(item, dict) for item in links):
        raise NeuralInterpretationError("Evidence links must be objects")
    try:
        return sorted(
            copy.deepcopy(links),
            key=lambda item: (
                item["candidate_occurrence_id"],
                item["evidence_occurrence_id"],
                item["kind"],
            ),
        )
    except KeyError as exc:
        raise NeuralInterpretationError("Evidence link fields are required") from exc


def ingest_model_response(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    request: dict[str, Any],
    raw_output: bytes,
    response: dict[str, Any],
) -> dict[str, Any]:
    """Consume one external model response without invoking or trusting a model."""
    if not isinstance(raw_output, bytes) or len(raw_output) > MAX_RAW_OUTPUT_BYTES:
        raise NeuralInterpretationError("Raw model output must be bounded bytes")

    verified_request = verify_request(contract, sources, request)
    response = _validate_response_shape(response)
    if response["request_sha256"] != verified_request["request_sha256"]:
        raise NeuralInterpretationError("Model response is bound to a different request")

    trace = _validate_model_trace(response["model_trace"], raw_output)
    model = response["model"]
    if not isinstance(model, dict) or set(model) != {
        "adapter_id", "model_family", "model_version", "context_sha256"
    }:
        raise NeuralInterpretationError("Invalid AE-27 model metadata")
    if (
        model["adapter_id"] != trace["adapter_id"]
        or model["model_family"] != trace["model_family"]
        or model["model_version"] != trace["model_version"]
    ):
        raise NeuralInterpretationError("Model metadata disagrees with model trace")

    expected_context = _context_digest(
        verified_request["base_graph_fingerprint"],
        verified_request["base_semantic_fingerprint"],
        verified_request["context_occurrences"],
    )
    if model["context_sha256"] != expected_context:
        raise NeuralInterpretationError("Model context digest mismatch")

    response_body = _body_without_digest(response, "response_sha256")
    expected_response_digest = _sha_json(response_body)
    if response.get("response_sha256") != expected_response_digest:
        raise NeuralInterpretationError("Model response digest mismatch")

    proposal = {
        "schema_version": AE27_SCHEMA,
        "proposal_id": response["proposal_id"],
        "base_contract_sha256": verified_request["base_contract_sha256"],
        "base_graph_fingerprint": verified_request["base_graph_fingerprint"],
        "base_semantic_fingerprint": verified_request["base_semantic_fingerprint"],
        "base_hypothesis_fingerprint": verified_request["base_hypothesis_fingerprint"],
        "context_occurrences": list(verified_request["context_occurrences"]),
        "candidate_assertions": _canonicalize_candidates(response["candidate_assertions"]),
        "evidence_links": _canonicalize_links(response["evidence_links"]),
        "model": {
            "adapter_id": trace["adapter_id"],
            "model_family": trace["model_family"],
            "model_version": trace["model_version"],
            "context_sha256": expected_context,
        },
    }
    proposal["proposal_sha256"] = _sha_json(proposal)
    try:
        meta = validate_proposal(contract, sources, proposal)
    except ProposalError as exc:
        raise NeuralInterpretationError(f"AE-27 rejected model interpretation: {exc}") from exc

    interpretation = {
        "schema_version": INTERPRETATION_SCHEMA,
        "request_sha256": verified_request["request_sha256"],
        "response_sha256": expected_response_digest,
        "proposal_sha256": meta["proposal_sha256"],
        "base_contract_sha256": verified_request["base_contract_sha256"],
        "base_graph_fingerprint": verified_request["base_graph_fingerprint"],
        "base_semantic_fingerprint": verified_request["base_semantic_fingerprint"],
        "base_hypothesis_fingerprint": verified_request["base_hypothesis_fingerprint"],
        "vocabulary_digest": verified_request["vocabulary_digest"],
        "model_trace": trace,
        "proposal": proposal,
        "authority": {
            "model_output_verified": False,
            "semantic_truth_verified": False,
            "candidate_only": True,
            "automatic_graph_mutation_permitted": False,
            "candidate_promoted_to_authoritative_fact": False,
        },
    }
    interpretation["interpretation_sha256"] = _sha_json(interpretation)
    return interpretation


def verify_interpretation(
    contract: dict[str, Any],
    sources: Mapping[str, bytes],
    request: dict[str, Any],
    raw_output: bytes,
    response: dict[str, Any],
    claimed: dict[str, Any],
) -> bool:
    """Recompute the complete AE-28 interpretation and compare exactly."""
    expected = ingest_model_response(contract, sources, request, raw_output, response)
    if claimed != expected:
        raise NeuralInterpretationError("Neural interpretation does not match exact source replay")
    return True


def response_from_canonical_bytes(raw_output: bytes) -> dict[str, Any]:
    """Parse a canonical JSON model response for the deterministic adapter path."""
    if not isinstance(raw_output, bytes) or len(raw_output) > MAX_RESPONSE_BYTES:
        raise NeuralInterpretationError("Model response is too large")
    try:
        value = json.loads(raw_output)
    except (ValueError, UnicodeError) as exc:
        raise NeuralInterpretationError("Model response is not valid JSON") from exc
    if canonical(value) != raw_output:
        raise NeuralInterpretationError("Model response must be canonical JSON")
    return _validate_response_shape(value)


def canonical_response_bytes(response: dict[str, Any]) -> bytes:
    """Serialize a normalized model response without changing its semantics."""
    return canonical(response)


__all__ = [
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "INTERPRETATION_SCHEMA",
    "NeuralInterpretationError",
    "NeuralRequest",
    "make_request",
    "verify_request",
    "ingest_model_response",
    "verify_interpretation",
    "response_from_canonical_bytes",
    "canonical_response_bytes",
]

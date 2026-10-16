"""AE-28 provider-neutral neural/LLM interpretation boundary."""

from .model_adapter import ModelRun, NeuralModelAdapter, ReplayNeuralAdapter

from .adapter import (
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    INTERPRETATION_SCHEMA,
    NeuralInterpretationError,
    NeuralRequest,
    make_request,
    verify_request,
    ingest_model_response,
    verify_interpretation,
    response_from_canonical_bytes,
    canonical_response_bytes,
)

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
    "ModelRun",
    "NeuralModelAdapter",
    "ReplayNeuralAdapter",
]

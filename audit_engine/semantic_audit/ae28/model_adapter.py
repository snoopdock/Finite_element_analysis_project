"""Provider interface for future AE-28 neural/LLM runtimes.

The protocol is deliberately small: the audit core supplies a canonical
request envelope and receives raw bytes plus a normalized response. Provider
authentication, prompt construction, network transport, and model execution
remain outside the semantic core.

A future runtime may implement this protocol; CI can instead use the
ReplayNeuralAdapter below with recorded response fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ModelRun:
    """Provider output supplied to AE-28 ingestion."""

    raw_output: bytes
    response: Mapping[str, Any]


class NeuralModelAdapter(Protocol):
    """Minimal provider-neutral interface for a future LLM/neural adapter."""

    adapter_id: str
    model_family: str
    model_version: str

    def generate(self, request: Mapping[str, Any]) -> ModelRun:
        """Return raw model bytes and a normalized AE-28 response.

        Implementations must not claim semantic authority. The AE-28 ingestion
        layer independently validates the response and binds it to repository
        state.
        """
        ...


class ReplayNeuralAdapter:
    """Deterministic adapter for recorded model-response fixtures."""

    def __init__(
        self,
        *,
        adapter_id: str,
        model_family: str,
        model_version: str,
        raw_output: bytes,
        response: Mapping[str, Any],
    ) -> None:
        self.adapter_id = adapter_id
        self.model_family = model_family
        self.model_version = model_version
        self._raw_output = bytes(raw_output)
        self._response = dict(response)

    def generate(self, request: Mapping[str, Any]) -> ModelRun:
        """Return the recorded response without inspecting or mutating request state."""
        return ModelRun(
            raw_output=self._raw_output,
            response=dict(self._response),
        )


__all__ = ["ModelRun", "NeuralModelAdapter", "ReplayNeuralAdapter"]

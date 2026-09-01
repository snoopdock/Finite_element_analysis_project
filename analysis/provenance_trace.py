#!/usr/bin/env python3
"""Auditable derivation/provenance trace records for scientific processing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProvenanceTrace:
    trace_id: str
    operation: str
    input_ids: List[str] = field(default_factory=list)
    output_ids: List[str] = field(default_factory=list)
    model: str | None = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: str | None = None
    software_version: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "operation": self.operation,
            "input_ids": list(self.input_ids),
            "output_ids": list(self.output_ids),
            "model": self.model,
            "parameters": dict(self.parameters),
            "timestamp": self.timestamp,
            "software_version": self.software_version,
        }


def trace_id_from_payload(
    operation: str,
    input_ids: List[str],
    output_ids: List[str],
    parameters: Dict[str, Any],
) -> str:
    payload = {
        "operation": str(operation).strip(),
        "input_ids": sorted(str(value).strip() for value in input_ids or [] if str(value).strip()),
        "output_ids": sorted(str(value).strip() for value in output_ids or [] if str(value).strip()),
        "parameters": parameters or {},
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "trace-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def normalize_provenance_trace(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    operation = str(value.get("operation", "")).strip()
    if not operation:
        return None

    def clean(values: Any) -> List[str]:
        result: List[str] = []
        seen = set()
        for item in values or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return sorted(result)

    input_ids = clean(value.get("input_ids"))
    output_ids = clean(value.get("output_ids"))
    parameters = value.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}
    trace = ProvenanceTrace(
        trace_id=str(value.get("trace_id") or trace_id_from_payload(operation, input_ids, output_ids, parameters)),
        operation=operation,
        input_ids=input_ids,
        output_ids=output_ids,
        model=str(value.get("model") or "").strip() or None,
        parameters=dict(parameters),
        timestamp=str(value.get("timestamp") or "").strip() or None,
        software_version=str(value.get("software_version") or "").strip() or None,
    )
    return trace.to_dict()

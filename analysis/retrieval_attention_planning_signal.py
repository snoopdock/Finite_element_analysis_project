#!/usr/bin/env python3
"""Translate R7B AttentionProposal objects into R8 ResearchPlanningSignals.

R8.2 is an explicit, lossy semantic boundary. This module does not mutate
retrieval history, attention proposals, lifecycle history, scientific state,
or acquisition systems. It only creates a planning-input representation.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from utils.text import utcnow


PLANNING_SIGNAL_SCHEMA_VERSION = 1
TRANSLATION_POLICY_VERSION = "r8.2-v1"
SIGNAL_TYPE = "acquisition_constraint"

REQUIRED_PROPOSAL_FIELDS = {
    "attention_id", "policy_version", "query_scope", "provider", "attention_reason",
    "observed_condition", "lifecycle_status", "supporting_event_ids",
    "recommended_acquisition_action",
}

ALLOWED_CONDITIONS = {
    "provider_unavailable", "provider_partially_available", "query_returned_empty_result",
    "repeated_query_provider_non_success", "repeated_query_provider_empty_result",
}

ALLOWED_SIGNAL_FIELDS = {
    "research_planning_signal_id", "source_attention_id", "schema_version", "signal_type",
    "target", "provenance", "operational_condition", "acquisition_constraint",
    "planning_context", "translation_policy_version", "created_at",
}
ALLOWED_TARGET_FIELDS = {"query_scope", "provider", "topic_scope", "proposition_reference"}
ALLOWED_OPERATIONAL_CONDITION_FIELDS = {"observed_condition"}
ALLOWED_ACQUISITION_CONSTRAINT_FIELDS = {"provider_access_limitation", "empty_query_result", "provider", "query_scope"}
ALLOWED_PROVENANCE_FIELDS = {"supporting_event_ids"}

FORBIDDEN_SEMANTIC_KEYS = {
    "confidence", "confidence_score", "evidence_strength", "evidence_gap", "epistemic_status",
    "truth_status", "truth_probability", "claim_rank", "claim_ranking", "ranking_score",
    "convergence_score", "convergence_state", "scientific_priority", "scientific_relevance",
    "scientific_importance", "scientific_resolution", "scientific_uncertainty", "claim_support",
    "evidence_quality",
}


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_event_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("supporting_event_ids must be a non-empty list")
    result = []
    seen = set()
    for event_id in value:
        normalized = _require_non_empty_string(event_id, "supporting_event_id")
        if normalized in seen:
            raise ValueError("supporting_event_ids must not contain duplicates")
        seen.add(normalized)
        result.append(normalized)
    return result


def _reject_unknown_fields(value: Mapping[str, Any], allowed: set[str], scope: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown {scope} fields: {unknown}")


def _contains_forbidden_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().casefold()
            if normalized in FORBIDDEN_SEMANTIC_KEYS:
                return str(key)
            found = _contains_forbidden_key(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _contains_forbidden_key(child)
            if found is not None:
                return found
    return None


def _validate_attention_proposal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(proposal, Mapping):
        raise TypeError("attention proposal must be a mapping")
    missing = sorted(REQUIRED_PROPOSAL_FIELDS - set(proposal))
    if missing:
        raise ValueError(f"attention proposal is missing required fields: {missing}")
    normalized = deepcopy(dict(proposal))
    _require_non_empty_string(normalized["attention_id"], "attention_id")
    _require_non_empty_string(normalized["policy_version"], "policy_version")
    try:
        _require_non_empty_string(normalized["query_scope"], "query_scope")
    except ValueError as exc:
        raise ValueError(f"ResearchPlanningSignal validation failed: {exc}") from exc
    _require_non_empty_string(normalized["provider"], "provider")
    _require_non_empty_string(normalized["attention_reason"], "attention_reason")
    _require_non_empty_string(normalized["recommended_acquisition_action"], "recommended_acquisition_action")
    _require_event_ids(normalized["supporting_event_ids"])
    condition = _require_non_empty_string(normalized["observed_condition"], "observed_condition")
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError(f"unsupported observed_condition: {condition!r}")
    if normalized["lifecycle_status"] != "open":
        raise ValueError("R8.2 requires the canonical R7B proposal lifecycle_status to be 'open'")
    return normalized


def _signal_id(source_attention_id: str, policy_version: str, condition: str, target: Mapping[str, Any], supporting_event_ids: list[str]) -> str:
    payload = {
        "translation_policy_version": TRANSLATION_POLICY_VERSION,
        "source_attention_id": source_attention_id,
        "policy_version": policy_version,
        "signal_type": SIGNAL_TYPE,
        "observed_condition": condition,
        "target": dict(target),
        "supporting_event_ids": list(supporting_event_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"planning-signal-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _constraint(condition: str, provider: str, query_scope: str) -> dict[str, Any]:
    if condition in {"provider_unavailable", "provider_partially_available", "repeated_query_provider_non_success"}:
        return {"provider_access_limitation": True, "provider": provider, "query_scope": query_scope}
    return {"empty_query_result": True, "provider": provider, "query_scope": query_scope}


def _make_signal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    source = _validate_attention_proposal(proposal)
    source_id = source["attention_id"].strip()
    policy_version = source["policy_version"].strip()
    query_scope = source["query_scope"].strip()
    provider = source["provider"].strip()
    condition = source["observed_condition"].strip()
    event_ids = _require_event_ids(source["supporting_event_ids"])
    target = {"query_scope": query_scope, "provider": provider}
    signal = {
        "research_planning_signal_id": _signal_id(source_id, policy_version, condition, target, event_ids),
        "source_attention_id": source_id,
        "schema_version": PLANNING_SIGNAL_SCHEMA_VERSION,
        "signal_type": SIGNAL_TYPE,
        "target": target,
        "operational_condition": {"observed_condition": condition},
        "acquisition_constraint": _constraint(condition, provider, query_scope),
        "provenance": {"supporting_event_ids": event_ids},
        "translation_policy_version": TRANSLATION_POLICY_VERSION,
    }
    validate_research_planning_signal(signal)
    return signal


def translate_attention_proposal(proposal: Mapping[str, Any], *, include_created_at: bool = False) -> dict[str, Any]:
    signal = _make_signal(proposal)
    if include_created_at:
        signal["created_at"] = utcnow()
    return signal


def translate_attention_proposals(proposals: list[Mapping[str, Any]], *, include_created_at: bool = False) -> list[dict[str, Any]]:
    if not isinstance(proposals, list):
        raise TypeError("proposals must be a list")
    signals = [translate_attention_proposal(proposal, include_created_at=include_created_at) for proposal in proposals]
    signals.sort(key=lambda item: item["research_planning_signal_id"])
    return signals


def validate_research_planning_signal(signal: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(signal, Mapping):
        raise TypeError("research planning signal must be a mapping")

    forbidden = _contains_forbidden_key(signal)
    if forbidden is not None:
        raise ValueError(f"forbidden scientific semantic field: {forbidden!r}")
    _reject_unknown_fields(signal, ALLOWED_SIGNAL_FIELDS, "ResearchPlanningSignal")

    required = ("research_planning_signal_id", "source_attention_id", "schema_version", "signal_type", "target", "provenance")
    missing = [field for field in required if field not in signal]
    if missing:
        raise ValueError(f"ResearchPlanningSignal is missing required fields: {missing}")

    result = deepcopy(dict(signal))
    _require_non_empty_string(result["research_planning_signal_id"], "research_planning_signal_id")
    _require_non_empty_string(result["source_attention_id"], "source_attention_id")
    if result["schema_version"] != PLANNING_SIGNAL_SCHEMA_VERSION:
        raise ValueError("unsupported ResearchPlanningSignal schema version")
    if result["signal_type"] != SIGNAL_TYPE:
        raise ValueError(f"unsupported signal_type: {result['signal_type']!r}")

    target = result["target"]
    if not isinstance(target, Mapping):
        raise ValueError("target must be a mapping")
    _reject_unknown_fields(target, ALLOWED_TARGET_FIELDS, "target")
    for field in ("query_scope", "provider", "topic_scope", "proposition_reference"):
        if field in target and target[field] is not None:
            _require_non_empty_string(target[field], f"target.{field}")

    provenance = result["provenance"]
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance must be a mapping")
    _reject_unknown_fields(provenance, ALLOWED_PROVENANCE_FIELDS, "provenance")
    _require_event_ids(provenance.get("supporting_event_ids"))

    if "translation_policy_version" in result:
        _require_non_empty_string(result["translation_policy_version"], "translation_policy_version")
    if "created_at" in result:
        _require_non_empty_string(result["created_at"], "created_at")

    if "operational_condition" in result:
        condition_data = result["operational_condition"]
        if not isinstance(condition_data, Mapping):
            raise ValueError("operational_condition must be a mapping")
        _reject_unknown_fields(condition_data, ALLOWED_OPERATIONAL_CONDITION_FIELDS, "operational_condition")
        condition = _require_non_empty_string(condition_data.get("observed_condition"), "operational_condition.observed_condition")
        if condition not in ALLOWED_CONDITIONS:
            raise ValueError(f"unsupported observed_condition: {condition!r}")

    if "acquisition_constraint" in result:
        constraint = result["acquisition_constraint"]
        if not isinstance(constraint, Mapping):
            raise ValueError("acquisition_constraint must be a mapping")
        _reject_unknown_fields(constraint, ALLOWED_ACQUISITION_CONSTRAINT_FIELDS, "acquisition_constraint")
        for field in ("provider", "query_scope"):
            if field in constraint:
                _require_non_empty_string(constraint[field], f"acquisition_constraint.{field}")
        for field in ("provider_access_limitation", "empty_query_result"):
            if field in constraint and not isinstance(constraint[field], bool):
                raise ValueError(f"acquisition_constraint.{field} must be boolean")

    if "planning_context" in result:
        raise ValueError("planning_context is reserved by R8.1 but is not implemented by R8.2")
    return result


__all__ = ["ALLOWED_CONDITIONS", "PLANNING_SIGNAL_SCHEMA_VERSION", "SIGNAL_TYPE", "TRANSLATION_POLICY_VERSION", "translate_attention_proposal", "translate_attention_proposals", "validate_research_planning_signal"]

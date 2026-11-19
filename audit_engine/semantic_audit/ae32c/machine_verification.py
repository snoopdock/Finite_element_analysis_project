"""Deterministic, machine-only verification of AE-32C evidence integrity.

This module verifies evidence identifiers, exact source lines, snapshot hashes,
and graph provenance. It does not judge semantic entailment, causal correctness,
or model quality. Follow-up actions are emitted as inert plans and never run.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "ae32c/machine-verification/v1"
PLAN_SCHEMA_VERSION = "ae32c/deterministic-follow-up-plan/v1"
_LINE = re.compile(r"^(\d+): ?(.*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GRAPH_TOOLS = frozenset({"graph_neighbors", "graph_path", "trace_execution_context",
                          "find_related_tests", "find_workflow_context"})


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _result(entry: Any) -> Mapping[str, Any]:
    response = _field(entry, "response", {})
    result = response.get("result", {}) if isinstance(response, Mapping) else {}
    return result if isinstance(result, Mapping) else {}


def _entry_provenance(entry: Any) -> Mapping[str, Any]:
    value = _field(entry, "provenance", {})
    return value if isinstance(value, Mapping) else {}


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _line_map(content: Any) -> dict[int, str]:
    if not isinstance(content, str):
        return {}
    result: dict[int, str] = {}
    for item in content.splitlines():
        match = _LINE.match(item)
        if match:
            result[int(match.group(1))] = match.group(2)
    return result


def _verify_source_reference(
    reference: Mapping[str, Any],
    *,
    ledger: Mapping[str, Any],
    repo_root: Path,
    expected_file_hashes: Mapping[str, str],
) -> dict[str, Any]:
    evidence_id = reference.get("evidence_id")
    path = _safe_relative_path(reference.get("path"))
    line = reference.get("line")
    digest = reference.get("source_sha256")
    result = {"evidence_id": evidence_id, "path": path, "line": line, "status": "failed"}
    if (not isinstance(evidence_id, str) or path is None
            or isinstance(line, bool) or not isinstance(line, int) or line < 1
            or not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
        result["reason"] = "source_reference_shape_invalid"
        return result
    entry = ledger.get(evidence_id)
    if entry is None or _field(entry, "status") != "ok" or _field(entry, "tool") != "read_source_file":
        result["reason"] = "source_read_evidence_missing_or_not_successful"
        return result
    read_result = _result(entry)
    if read_result.get("path") != path or read_result.get("source_sha256") != digest:
        result["reason"] = "source_reference_does_not_match_ledger_read"
        return result
    if read_result.get("content_omitted") is True or line not in _line_map(read_result.get("content")):
        result["reason"] = "cited_line_not_present_in_complete_ledger_read"
        return result
    if expected_file_hashes.get(path) != digest:
        result["reason"] = "source_reference_hash_differs_from_snapshot_manifest"
        return result

    root = repo_root.resolve(strict=True)
    candidate = root.joinpath(*PurePosixPath(path).parts)
    current = root
    for part in PurePosixPath(path).parts:
        current = current / part
        if current.is_symlink():
            result["reason"] = "source_path_contains_symlink"
            return result
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        raw = resolved.read_bytes()
    except (OSError, ValueError):
        result["reason"] = "source_path_unavailable_or_outside_repository"
        return result
    current_digest = hashlib.sha256(raw).hexdigest()
    if current_digest != digest:
        result["reason"] = "current_source_hash_differs_from_read_snapshot"
        return result
    result.update({"status": "passed", "reason": "ledger_line_and_current_source_hash_match",
                   "source_sha256": digest})
    return result


def build_machine_verification_assessment(
    *,
    diagnosis: Any,
    claim_assessment: Mapping[str, Any],
    ledger_entries: Sequence[Any],
    repo_root: str | Path,
    expected_file_hashes: Mapping[str, str],
    expected_manifest_sha256: str | None,
    expected_graph_fingerprint: str | None,
    snapshot_status: str,
) -> dict[str, Any]:
    """Verify source/graph evidence integrity without assigning semantic truth."""
    if not isinstance(diagnosis, Mapping) or not isinstance(claim_assessment, Mapping):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "not_available",
            "semantic_correctness": "not_assessed",
            "diagnostic_accuracy": "not_assessed",
            "human_review_required": False,
            "items": [],
            "summary": {"item_count": 0, "verified_source_reference_count": 0,
                        "invalid_source_reference_count": 0, "runtime_claim_count": 0},
        }

    root = Path(repo_root).expanduser().resolve(strict=True)
    ledger = {
        str(_field(entry, "evidence_id")): entry
        for entry in ledger_entries
        if isinstance(_field(entry, "evidence_id"), str)
    }
    items: list[dict[str, Any]] = []
    for claim in claim_assessment.get("items", []):
        if not isinstance(claim, Mapping):
            continue
        evidence_ids = claim.get("evidence_refs", [])
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        evidence_checks = []
        for evidence_id in evidence_ids:
            entry = ledger.get(evidence_id) if isinstance(evidence_id, str) else None
            evidence_checks.append({
                "evidence_id": evidence_id,
                "status": "passed" if entry is not None and _field(entry, "status") == "ok" else "failed",
            })

        raw_refs = claim.get("source_references", [])
        if not isinstance(raw_refs, list):
            raw_refs = []
        source_checks = [
            _verify_source_reference(
                item, ledger=ledger, repo_root=root,
                expected_file_hashes=expected_file_hashes,
            )
            for item in raw_refs if isinstance(item, Mapping)
        ]

        graph_checks = []
        for evidence_id in evidence_ids:
            entry = ledger.get(evidence_id) if isinstance(evidence_id, str) else None
            if entry is None or _field(entry, "tool") not in _GRAPH_TOOLS:
                continue
            provenance = _entry_provenance(entry)
            graph_ok = (
                _field(entry, "status") == "ok"
                and provenance.get("source_manifest_sha256") == expected_manifest_sha256
                and provenance.get("graph_fingerprint") == expected_graph_fingerprint
            )
            graph_checks.append({
                "evidence_id": evidence_id,
                "status": "passed" if graph_ok else "failed",
                "graph_fingerprint": provenance.get("graph_fingerprint"),
                "source_manifest_sha256": provenance.get("source_manifest_sha256"),
            })

        invalid = (
            any(item["status"] != "passed" for item in evidence_checks)
            or any(item["status"] != "passed" for item in source_checks)
            or any(item["status"] != "passed" for item in graph_checks)
        )
        claim_type = str(claim.get("claim_type", "observation"))
        runtime_claim = claim_type in {"runtime_claim", "causal_hypothesis"}
        direct_source_verified = bool(source_checks) and all(item["status"] == "passed" for item in source_checks)
        if invalid:
            machine_status = "evidence_integrity_failed"
        elif direct_source_verified:
            machine_status = "evidence_integrity_passed_semantics_unassessed"
        else:
            machine_status = "incomplete_no_verified_direct_source_reference"
        items.append({
            "claim_id": claim.get("claim_id"),
            "claim_type": claim_type,
            "machine_status": machine_status,
            "evidence_id_checks": evidence_checks,
            "source_reference_checks": source_checks,
            "graph_provenance_checks": graph_checks,
            "available_uncited_source_candidates": [
                {
                    "evidence_id": candidate.get("evidence_id"),
                    "path": _safe_relative_path(candidate.get("path")),
                    "line": candidate.get("line"),
                    "source_sha256": candidate.get("source_sha256"),
                }
                for candidate in claim.get("available_uncited_source_candidates", [])
                if isinstance(candidate, Mapping)
                and _safe_relative_path(candidate.get("path")) is not None
                and isinstance(candidate.get("evidence_id"), str)
                and isinstance(candidate.get("line"), int)
                and not isinstance(candidate.get("line"), bool)
                and isinstance(candidate.get("source_sha256"), str)
                and _SHA256.fullmatch(candidate.get("source_sha256"))
            ][:20],
            "runtime_reproduction_status": "not_performed_read_only" if runtime_claim else "not_required_for_claim_type",
            "semantic_entailment": "not_assessed",
            "causal_correctness": "not_assessed",
        })

    invalid_count = sum(
        1 for item in items if item["machine_status"] == "evidence_integrity_failed"
    )
    incomplete_count = sum(
        1 for item in items if item["machine_status"] == "incomplete_no_verified_direct_source_reference"
    )
    source_count = sum(len(item["source_reference_checks"]) for item in items)
    verified_source_count = sum(
        1 for item in items for ref in item["source_reference_checks"] if ref["status"] == "passed"
    )
    runtime_count = sum(item["claim_type"] in {"runtime_claim", "causal_hypothesis"} for item in items)
    if invalid_count:
        status = "failed"
    elif snapshot_status != "verified" or incomplete_count:
        status = "incomplete"
    else:
        status = "evidence_integrity_passed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "scope": "evidence_id_integrity_exact_source_line_linkage_current_source_hash_and_graph_provenance",
        "semantic_correctness": "not_assessed",
        "diagnostic_accuracy": "not_assessed",
        "runtime_reproduction_status": "not_performed_read_only",
        "human_review_required": False,
        "accuracy_claim_permitted": False,
        "source_snapshot_status": snapshot_status,
        "source_manifest_sha256": expected_manifest_sha256,
        "graph_fingerprint": expected_graph_fingerprint,
        "items": items,
        "summary": {
            "item_count": len(items),
            "verified_source_reference_count": verified_source_count,
            "source_reference_count": source_count,
            "invalid_source_reference_count": sum(
                1 for item in items for ref in item["source_reference_checks"] if ref["status"] != "passed"
            ),
            "invalid_claim_count": invalid_count,
            "incomplete_claim_count": incomplete_count,
            "runtime_or_causal_claim_count": runtime_count,
            "runtime_or_causal_claims_reproduced": 0,
        },
    }


def build_deterministic_follow_up_plan(assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Create an inert, deterministic plan of bounded verification follow-ups."""
    actions: list[dict[str, Any]] = []
    for item in assessment.get("items", []) if isinstance(assessment, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        claim_id = str(item.get("claim_id", "unknown"))
        if item.get("machine_status") == "evidence_integrity_failed":
            actions.append({
                "action_type": "rebuild_source_snapshot_and_reverify",
                "claim_id": claim_id,
                "status": "required",
                "reason": "one_or_more_evidence_bindings_failed",
            })
        elif item.get("machine_status") == "incomplete_no_verified_direct_source_reference":
            actions.append({
                "action_type": "collect_direct_source_evidence",
                "claim_id": claim_id,
                "status": "required",
                "candidate_source_ranges": item.get("available_uncited_source_candidates", []),
                "reason": "no_verified_direct_source_reference",
            })
        if item.get("claim_type") in {"runtime_claim", "causal_hypothesis"}:
            actions.append({
                "action_type": "run_registered_runtime_witness",
                "claim_id": claim_id,
                "status": "blocked_no_registered_harness_binding",
                "reason": "runtime_or_causal_claim_requires_a_trusted_registered_witness",
            })
    actions.sort(key=lambda row: (row["claim_id"], row["action_type"]))
    identity = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "assessment_status": assessment.get("status", "unknown") if isinstance(assessment, Mapping) else "unknown",
        "source_manifest_sha256": assessment.get("source_manifest_sha256") if isinstance(assessment, Mapping) else None,
        "graph_fingerprint": assessment.get("graph_fingerprint") if isinstance(assessment, Mapping) else None,
        "actions": actions,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        **identity,
        "plan_id": "plan:" + digest[:28],
        "execution_mode": "plan_only",
        "actions_executed": 0,
        "shell_execution_permitted": False,
        "repository_code_execution_permitted": False,
        "source_mutation_permitted": False,
        "arbitrary_model_supplied_action_permitted": False,
    }

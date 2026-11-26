"""Deterministic source-unit and extractor-candidate reconciliation for M7.5.12.

This module inventories tracked source units from a verified AE-32C source
snapshot and derives extractor candidates from a built-in, versioned registry.
It does not execute extractors or assert that either inventory is universally
exhaustive.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

SOURCE_MANIFEST_SCHEMA = "ae32c/source-snapshot-manifest/v1"
INVENTORY_SCHEMA = "ae32c/source-extractor-inventory/v1"
REGISTRY_SCHEMA = "ae32c/extractor-candidate-registry/v1"
REGISTRY_ID = "ae32c-built-in-extractor-candidate-registry"
REGISTRY_VERSION = "1.0.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# This registry describes candidate eligibility, not extractor execution.
# New extractor families require an explicit, reviewed registry change.
_EXTRACTORS = (
    {
        "extractor_id": "python_ast",
        "version": "1.0.0",
        "candidate_kind": "python_source",
        "suffixes": (".py",),
    },
    {
        "extractor_id": "workflow_static_scan",
        "version": "1.0.0",
        "candidate_kind": "github_actions_workflow",
        "suffixes": (".yml", ".yaml"),
    },
)


class SourceExtractorInventoryError(ValueError):
    """A source/extractor inventory cannot be reconciled safely."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def extractor_candidate_registry() -> dict[str, Any]:
    payload = {
        "schema": REGISTRY_SCHEMA,
        "registry_id": REGISTRY_ID,
        "version": REGISTRY_VERSION,
        "extractors": [
            {
                "extractor_id": item["extractor_id"],
                "version": item["version"],
                "candidate_kind": item["candidate_kind"],
                "suffixes": list(item["suffixes"]),
            }
            for item in _EXTRACTORS
        ],
    }
    return {**payload, "registry_sha256": _digest(payload)}


def _verified_source_entries(source_manifest: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(source_manifest, Mapping):
        raise SourceExtractorInventoryError("source_manifest_must_be_an_object")
    manifest = dict(source_manifest)
    if manifest.get("manifest_schema") != SOURCE_MANIFEST_SCHEMA:
        raise SourceExtractorInventoryError("source_manifest_schema_invalid")
    if manifest.get("status") != "VERIFIED":
        raise SourceExtractorInventoryError("source_manifest_not_postflight_verified")
    verification = manifest.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "VERIFIED":
        raise SourceExtractorInventoryError("source_manifest_verification_not_verified")
    submitted_digest = manifest.get("manifest_sha256")
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if not isinstance(submitted_digest, str) or submitted_digest != _digest(payload):
        raise SourceExtractorInventoryError("source_manifest_digest_mismatch")
    snapshot_id = manifest.get("source_snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise SourceExtractorInventoryError("source_snapshot_identity_missing")
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, Mapping):
        raise SourceExtractorInventoryError("source_inventory_missing")
    entries = inventory.get("entries")
    if not isinstance(entries, list) or inventory.get("entry_count") != len(entries):
        raise SourceExtractorInventoryError("source_inventory_count_invalid")
    if inventory.get("sha256") != _digest(entries):
        raise SourceExtractorInventoryError("source_inventory_digest_mismatch")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, Mapping):
            raise SourceExtractorInventoryError("source_inventory_entry_invalid")
        entry = dict(item)
        path = entry.get("path")
        if (
            not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/"))
            or path in seen
        ):
            raise SourceExtractorInventoryError("source_inventory_path_invalid_or_duplicate")
        seen.add(path)
        mode = entry.get("mode")
        object_type = entry.get("object_type")
        if object_type == "blob":
            if mode not in {"100644", "100755", "120000"}:
                raise SourceExtractorInventoryError("source_blob_mode_unsupported:" + path)
            if not isinstance(entry.get("content_sha256"), str) or not _SHA256_RE.fullmatch(entry["content_sha256"]):
                raise SourceExtractorInventoryError("source_blob_digest_invalid:" + path)
        elif object_type == "commit" and mode == "160000":
            if entry.get("content_sha256") is not None:
                raise SourceExtractorInventoryError("gitlink_must_not_claim_blob_digest:" + path)
        else:
            raise SourceExtractorInventoryError("source_object_type_unsupported:" + path)
        normalized.append(entry)

    expected_order = sorted(normalized, key=lambda row: row["path"].encode("utf-8"))
    if normalized != expected_order:
        raise SourceExtractorInventoryError("source_inventory_order_invalid")
    return snapshot_id, normalized


def build_source_extractor_inventory(
    source_manifest: Mapping[str, Any],
    *,
    scope_exclusions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic inventory from a verified source snapshot.

    Every source entry is retained and classified. Matching extractor
    candidates are recorded as CANDIDATE_NOT_EXECUTED. Explicit exclusions
    remain visible. Files without a registered extractor are reported rather
    than silently dropped. Gitlinks are separately classified as submodules.
    """
    source_snapshot_id, entries = _verified_source_entries(source_manifest)
    exclusions = dict(scope_exclusions or {})
    paths = {item["path"] for item in entries}
    for path, reason in exclusions.items():
        if path not in paths:
            raise SourceExtractorInventoryError("scope_exclusion_references_unknown_source:" + str(path))
        if not isinstance(reason, str) or not reason.strip():
            raise SourceExtractorInventoryError("scope_exclusion_requires_nonempty_reason:" + str(path))

    registry = extractor_candidate_registry()
    registry_payload = {key: value for key, value in registry.items() if key != "registry_sha256"}
    if registry["registry_sha256"] != _digest(registry_payload):
        raise SourceExtractorInventoryError("built_in_extractor_registry_integrity_failure")

    source_units: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        path = entry["path"]
        excluded = path in exclusions
        if entry["object_type"] == "commit":
            classification = "DECLARED_EXCLUDED" if excluded else "GITLINK_SUBMODULE"
        else:
            matches = [
                item for item in registry["extractors"]
                if any(path.lower().endswith(suffix) for suffix in item["suffixes"])
            ]
            if excluded:
                classification = "DECLARED_EXCLUDED"
            elif matches:
                classification = "EXTRACTOR_CANDIDATE"
            else:
                classification = "NO_REGISTERED_EXTRACTOR"
            for extractor in matches:
                candidate_payload = {
                    "source_path": path,
                    "source_content_sha256": entry["content_sha256"],
                    "extractor_id": extractor["extractor_id"],
                    "extractor_version": extractor["version"],
                    "candidate_kind": extractor["candidate_kind"],
                    "status": "DECLARED_EXCLUDED" if excluded else "CANDIDATE_NOT_EXECUTED",
                    "exclusion_reason": exclusions.get(path),
                }
                candidates.append({
                    "candidate_id": _digest(candidate_payload),
                    **candidate_payload,
                })
        source_units.append({
            "path": path,
            "mode": entry["mode"],
            "object_type": entry["object_type"],
            "content_sha256": entry["content_sha256"],
            "classification": classification,
            "exclusion_reason": exclusions.get(path),
        })

    candidates.sort(key=lambda row: (row["source_path"], row["extractor_id"]))
    source_units.sort(key=lambda row: row["path"])
    unsupported = tuple(
        row["path"] for row in source_units
        if row["classification"] == "NO_REGISTERED_EXTRACTOR"
    )
    gitlinks = tuple(
        row["path"] for row in source_units
        if row["classification"] == "GITLINK_SUBMODULE"
    )
    excluded_paths = tuple(sorted(exclusions))
    counts = {
        "source_unit_count": len(source_units),
        "extractor_candidate_count": len(candidates),
        "candidate_not_executed_count": sum(
            row["status"] == "CANDIDATE_NOT_EXECUTED" for row in candidates
        ),
        "declared_excluded_source_count": len(excluded_paths),
        "unsupported_source_count": len(unsupported),
        "gitlink_submodule_count": len(gitlinks),
    }
    payload = {
        "schema": INVENTORY_SCHEMA,
        "source_snapshot_id": source_snapshot_id,
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "registry_id": registry["registry_id"],
        "registry_version": registry["version"],
        "registry_sha256": registry["registry_sha256"],
        "source_units": source_units,
        "extractor_candidates": candidates,
        "unsupported_source_paths": list(unsupported),
        "gitlink_submodule_paths": list(gitlinks),
        "scope_exclusions": [
            {"path": path, "reason": exclusions[path]} for path in excluded_paths
        ],
        "counts": counts,
        "reconciliation": {
            "status": "RECONCILED",
            "all_source_entries_classified": len(source_units) == len(entries),
            "all_candidates_derived_from_registry": True,
            "unsupported_sources_explicit": True,
        },
        "authority": {
            "complete_relative_to_verified_source_manifest": True,
            "complete_relative_to_builtin_extractor_registry": True,
            "source_universe_universally_exhaustive": False,
            "extractor_universe_universally_exhaustive": False,
            "extractors_executed": False,
            "graph_completeness_established": False,
            "proposition_truth_established": False,
            "audit_decision_authority": False,
            "production_approval": False,
        },
    }
    return {**payload, "inventory_sha256": _digest(payload)}


def verify_source_extractor_inventory(
    source_manifest: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently rederive and compare the complete inventory payload."""
    if not isinstance(inventory, Mapping):
        raise SourceExtractorInventoryError("inventory_must_be_an_object")
    submitted = dict(inventory)
    submitted_digest = submitted.get("inventory_sha256")
    payload = {key: value for key, value in submitted.items() if key != "inventory_sha256"}
    if not isinstance(submitted_digest, str) or submitted_digest != _digest(payload):
        raise SourceExtractorInventoryError("inventory_digest_mismatch")
    exclusions_raw = submitted.get("scope_exclusions")
    if not isinstance(exclusions_raw, list):
        raise SourceExtractorInventoryError("inventory_scope_exclusions_invalid")
    exclusions: dict[str, str] = {}
    for item in exclusions_raw:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("path"), str)
            or item["path"] in exclusions
            or not isinstance(item.get("reason"), str)
        ):
            raise SourceExtractorInventoryError("inventory_scope_exclusion_entry_invalid")
        exclusions[item["path"]] = item["reason"]
    expected = build_source_extractor_inventory(source_manifest, scope_exclusions=exclusions)
    if _canonical_bytes(expected) != _canonical_bytes(submitted):
        raise SourceExtractorInventoryError("inventory_semantic_reconciliation_mismatch")
    return {
        "inventory_sha256": submitted_digest,
        "semantic_integrity": True,
        "source_unit_count": expected["counts"]["source_unit_count"],
        "extractor_candidate_count": expected["counts"]["extractor_candidate_count"],
        "unsupported_source_count": expected["counts"]["unsupported_source_count"],
        "gitlink_submodule_count": expected["counts"]["gitlink_submodule_count"],
        "extractors_executed": False,
        "universal_exhaustiveness_established": False,
    }

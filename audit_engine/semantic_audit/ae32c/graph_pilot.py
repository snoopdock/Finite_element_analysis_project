"""Matched graph-enabled/graph-disabled AE-32C repository pilot.

The pilot uses one immutable, bounded source slice and two independent
provider sessions. The only intended intervention is graph-tool availability
plus the corresponding instruction to use those tools in the treatment arm.
Repository code is parsed as text; it is never executed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
import uuid
from typing import Any, Callable, Mapping

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.ae32c.investigator import RepositoryInvestigator
from audit_engine.semantic_audit.ae32c.live_evaluation import build_live_investigation_limits
from providers.factory import SUPPORTED_PROVIDERS, build_provider


_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_GRAPH_PROFILES = _PACKAGE_ROOT / "evaluation" / "ae32c" / "graph_pilot_profiles.json"
_DEFAULT_PROVIDER_PROFILES = _PACKAGE_ROOT / "evaluation" / "ae32c" / "provider_model_profiles.json"
_MODEL_RE = re.compile(r"[A-Za-z0-9@._:/-]{1,200}")


class GraphPilotError(RuntimeError):
    """Raised when the bounded pilot cannot be prepared safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(payload, encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphPilotError(f"configuration_unavailable_or_invalid:{path.name}") from exc
    if not isinstance(value, dict):
        raise GraphPilotError(f"configuration_root_must_be_object:{path.name}")
    return value


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphPilotError("profile_path_must_be_non_empty_string")
    raw = value.strip()
    if "\\" in raw or raw.startswith("/"):
        raise GraphPilotError("profile_path_must_be_canonical_relative_path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise GraphPilotError("profile_path_traversal_rejected")
    return path.as_posix()


def _reject_symlink_components(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise GraphPilotError("profile_path_escaped_repository") from exc
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise GraphPilotError(f"symlinked_source_path_rejected:{relative.as_posix()}")


def _load_profile(profile_name: str, profile_path: Path = _DEFAULT_GRAPH_PROFILES) -> dict[str, Any]:
    config = _load_json(profile_path)
    if config.get("schema_version") != "ae32c/graph-pilot-profiles/v1":
        raise GraphPilotError("unsupported_graph_pilot_profile_schema")
    profiles = config.get("profiles")
    if not isinstance(profiles, Mapping):
        raise GraphPilotError("graph_pilot_profiles_missing")
    profile = profiles.get(profile_name)
    if not isinstance(profile, Mapping):
        raise GraphPilotError(f"unknown_graph_pilot_profile:{profile_name}")
    result = dict(profile)
    # Preserve compatibility with earlier v1 profiles that predate the
    # cross-module follow-through threshold.
    result.setdefault("graph_min_cross_module_reads", 1)
    for key in ("source_directories", "include_files", "graph_relation_types"):
        if not isinstance(result.get(key), list):
            raise GraphPilotError(f"profile_field_must_be_list:{key}")
    target = result.get("graph_target")
    if not isinstance(target, str) or not target.strip():
        raise GraphPilotError("profile_graph_target_missing")
    if not result["graph_relation_types"] or any(
        not isinstance(item, str) or not item.strip() for item in result["graph_relation_types"]
    ):
        raise GraphPilotError("profile_graph_relation_types_invalid")
    for key, minimum, maximum in (
        ("max_files", 1, 100),
        ("max_bytes", 1024, 2_000_000),
        ("graph_query_depth", 1, 3),
        ("graph_query_max_results", 1, 30),
        ("graph_min_cross_module_reads", 1, 10),
    ):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise GraphPilotError(f"profile_bound_invalid:{key}")
    return result


def build_scoped_snapshot(
    repo_root: Path,
    scope_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy an explicit, bounded Python-only slice while preserving repo-relative paths."""
    root = repo_root.resolve(strict=True)
    if not root.is_dir() or repo_root.is_symlink():
        raise GraphPilotError("repository_root_unavailable_or_symlinked")
    if scope_root.exists():
        if scope_root.is_symlink():
            raise GraphPilotError("scope_root_must_not_be_symlink")
        shutil.rmtree(scope_root)
    scope_root.mkdir(parents=True, exist_ok=False)

    selected: set[str] = set()
    for directory_value in profile["source_directories"]:
        directory = _safe_relative_path(directory_value)
        candidate = root / directory
        _reject_symlink_components(root, candidate)
        if not candidate.is_dir():
            raise GraphPilotError(f"profile_source_directory_missing:{directory}")
        for item in candidate.rglob("*.py"):
            if "__pycache__" in item.parts:
                continue
            _reject_symlink_components(root, item)
            if item.is_file():
                selected.add(item.relative_to(root).as_posix())

    for file_value in profile["include_files"]:
        relative = _safe_relative_path(file_value)
        if not relative.endswith(".py"):
            raise GraphPilotError(f"profile_only_allows_python_files:{relative}")
        candidate = root / relative
        _reject_symlink_components(root, candidate)
        if not candidate.is_file():
            raise GraphPilotError(f"profile_source_file_missing:{relative}")
        selected.add(relative)

    maximum_files = profile["max_files"]
    maximum_bytes = profile["max_bytes"]
    if len(selected) > maximum_files:
        raise GraphPilotError(f"scope_file_limit_exceeded:{len(selected)}>{maximum_files}")

    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for relative in sorted(selected):
        source = root / relative
        data = source.read_bytes()
        total_bytes += len(data)
        if total_bytes > maximum_bytes:
            raise GraphPilotError(f"scope_byte_limit_exceeded:{total_bytes}>{maximum_bytes}")
        destination = scope_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        entries.append({
            "path": relative,
            "size_bytes": len(data),
            "sha256": _sha256_bytes(data),
        })

    manifest = {
        "schema_version": "ae32c/graph-pilot-source-scope/v1",
        "profile": profile.get("description", ""),
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "files": entries,
    }
    manifest["manifest_sha256"] = _sha256_bytes(_canonical_json(manifest).encode("utf-8"))
    return manifest


def _graph_preflight(
    evidence_tools: RepositoryEvidenceTools,
    *,
    target: str,
    relation_types: tuple[str, ...],
    depth: int,
    max_results: int,
) -> dict[str, Any]:
    summary_response = evidence_tools.invoke("repository_summary", {})
    if summary_response.get("status") != "ok":
        raise GraphPilotError("repository_summary_preflight_failed")
    summary = summary_response.get("result", {})
    if not isinstance(summary, Mapping) or summary.get("audit_status") != "complete":
        raise GraphPilotError("repository_snapshot_incomplete")

    query_response = evidence_tools.invoke("graph_neighbors", {
        "node": target,
        # The pilot follows the target's outgoing CALLS chain. A bidirectional
        # depth-two preflight can exhaust the traversal's visited-node bound
        # with unrelated callers and falsely fail an otherwise complete target
        # investigation.
        "direction": "outgoing",
        "relation_types": list(relation_types),
        "max_depth": depth,
        "max_results": max_results,
    })
    if query_response.get("status") != "ok":
        error = query_response.get("error", {})
        raise GraphPilotError("graph_query_preflight_failed:" + str(error.get("code", "unknown")))
    result = query_response.get("result", {})
    if not isinstance(result, Mapping):
        raise GraphPilotError("graph_query_preflight_result_invalid")
    observed = set(result.get("observed_relation_types", []))
    if result.get("coverage_status") != "complete_for_query" or result.get("truncated") is True:
        raise GraphPilotError("graph_query_preflight_incomplete_or_truncated")
    if not observed.intersection(relation_types):
        raise GraphPilotError("required_graph_relationship_not_observed")
    if not result.get("source_paths"):
        raise GraphPilotError("graph_query_returned_no_source_paths")

    return {
        "schema_version": "ae32c/graph-pilot-preflight/v1",
        "passed": True,
        "repository_summary": {
            key: summary.get(key)
            for key in (
                "audit_status", "indexed_file_count", "graph_node_count", "graph_edge_count",
                "graph_relation_counts", "call_graph", "read_only", "repository_code_executed",
                "network_calls_performed", "source_files_modified",
            )
        },
        "graph_query": query_response,
    }


def _load_provider_model_profile(
    provider_name: str,
    model_name: str,
    profile_path: Path = _DEFAULT_PROVIDER_PROFILES,
) -> tuple[dict[str, Any], float]:
    config = _load_json(profile_path)
    if config.get("schema_version") != "ae32c/provider-model-evaluation-profiles/v1":
        raise GraphPilotError("unsupported_provider_model_profile_schema")
    default_pair_cap = config.get("default_pair_max_cost_usd", 1.0)
    if isinstance(default_pair_cap, bool) or not isinstance(default_pair_cap, (int, float)) or default_pair_cap <= 0:
        raise GraphPilotError("default_pair_cost_cap_invalid")
    providers = config.get("providers", {})
    provider = providers.get(provider_name, {}) if isinstance(providers, Mapping) else {}
    models = provider.get("models", {}) if isinstance(provider, Mapping) else {}
    model_profile = models.get(model_name, {}) if isinstance(models, Mapping) else {}
    return dict(model_profile) if isinstance(model_profile, Mapping) else {}, float(default_pair_cap)


_RUNTIME_LIMIT_KEYS = {
    "max_rounds",
    "max_tool_calls",
    "max_tokens_per_call",
    "finalization_max_tokens_per_call",
    "max_total_tokens",
    "max_response_chars",
    "max_tool_response_bytes",
    "max_tool_context_chars",
    "max_total_evidence_bytes",
    "max_total_prompt_chars",
    "max_elapsed_seconds",
    "finalization_rounds_reserved",
    "max_invalid_final_attempts",
    "max_invalid_json_retries",
    "max_finalization_invalid_json_retries",
    "max_finalization_recovery_retries",
    "finalization_prompt_tokens_reserved_per_round",
}


def _apply_model_runtime_limits(base_limits: Any, runtime_limits: Any) -> Any:
    """Apply bounded per-provider/model InvestigationLimits from the profile."""
    if runtime_limits is None:
        return base_limits
    if not isinstance(runtime_limits, Mapping):
        raise GraphPilotError("model_runtime_limits_must_be_an_object")
    unknown = sorted(set(runtime_limits) - _RUNTIME_LIMIT_KEYS)
    if unknown:
        raise GraphPilotError("unsupported_model_runtime_limit:" + ",".join(str(item) for item in unknown))
    try:
        return replace(base_limits, **dict(runtime_limits))
    except (TypeError, ValueError) as exc:
        raise GraphPilotError("model_runtime_limits_invalid:" + str(exc)) from exc


def _runtime_limits_record(limits: Any) -> dict[str, Any]:
    """Return the bounded execution limits that define a model's live run."""
    names = (
        "max_rounds",
        "max_tool_calls",
        "max_tokens_per_call",
        "finalization_max_tokens_per_call",
        "max_total_tokens",
        "max_elapsed_seconds",
        "finalization_rounds_reserved",
        "finalization_prompt_tokens_reserved_per_round",
        "max_tool_context_chars",
        "max_total_prompt_chars",
        "max_invalid_json_retries",
        "max_finalization_invalid_json_retries",
        "max_finalization_recovery_retries",
    )
    return {name: getattr(limits, name) for name in names}


def _rate(spec: Any) -> float:
    if not isinstance(spec, Mapping):
        raise GraphPilotError("model_pricing_rate_profile_invalid")
    env_name = spec.get("env")
    raw = os.environ.get(env_name, "") if isinstance(env_name, str) and env_name else ""
    value = spec.get("default") if not raw else raw
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GraphPilotError("model_pricing_rate_invalid") from exc
    if not math.isfinite(number) or number < 0:
        raise GraphPilotError("model_pricing_rate_invalid")
    return number


def _build_cost_estimator(
    provider_name: str,
    model_name: str,
    model_profile: Mapping[str, Any],
) -> Callable[[str, str, int, int], float] | None:
    pricing = model_profile.get("pricing")
    if pricing is None and (
        "input_usd_per_million_tokens" in model_profile
        or "output_usd_per_million_tokens" in model_profile
    ):
        pricing = model_profile
    if not isinstance(pricing, Mapping):
        return None
    input_rate = _rate(pricing.get("input_usd_per_million_tokens"))
    output_rate = _rate(pricing.get("output_usd_per_million_tokens"))
    output_multiplier = pricing.get("output_reservation_multiplier", 2)
    margin = pricing.get("uncertainty_margin", 0.15)
    if isinstance(output_multiplier, bool) or not isinstance(output_multiplier, int) or not 1 <= output_multiplier <= 4:
        raise GraphPilotError("model_pricing_output_multiplier_invalid")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not 0 <= float(margin) <= 1:
        raise GraphPilotError("model_pricing_margin_invalid")

    def estimate(_provider: str, _model: str, prompt_chars: int, output_tokens: int) -> float:
        if (
            isinstance(prompt_chars, bool) or not isinstance(prompt_chars, int) or prompt_chars < 0
            or isinstance(output_tokens, bool) or not isinstance(output_tokens, int) or output_tokens < 0
        ):
            raise ValueError("invalid_cost_estimator_input")
        input_tokens = math.ceil((prompt_chars / 4.0) * 1.25)
        output_reservation = output_tokens * output_multiplier
        base = (input_tokens * input_rate + output_reservation * output_rate) / 1_000_000.0
        return base * (1.0 + float(margin))

    estimate.pricing_metadata = {
        "provider": provider_name,
        "model": model_name,
        "input_usd_per_million_tokens": input_rate,
        "output_usd_per_million_tokens": output_rate,
        "output_reservation_multiplier": output_multiplier,
        "uncertainty_margin": float(margin),
        "cached_input_discount_assumed": False,
        "scope": "each_condition_of_matched_graph_pilot",
    }
    return estimate


def _make_provider(provider_name: str, model_name: str, *, max_calls: int, max_tokens: int):
    budget = {
        "max_llm_calls_per_run": max_calls,
        "max_tokens_per_call": max_tokens,
    }
    config = {
        "budget": dict(budget),
        "cloudflare_models": [model_name] if model_name else ["@cf/meta/llama-3.1-8b-instruct-fast"],
    }
    return build_provider(config, budget, provider_name, model_name, environ=os.environ)


def _effective_model(provider: Any, requested: str) -> str:
    if requested:
        return requested
    model = getattr(provider, "model", None)
    if isinstance(model, str) and model.strip():
        return model.strip()[:200]
    models = getattr(provider, "models", None)
    if isinstance(models, (list, tuple)) and models and isinstance(models[0], str):
        return models[0][:200]
    return "provider-default-not-reported"


def _condition_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    budget = report.get("budget", {})
    if not isinstance(budget, Mapping):
        budget = {}
    reads: set[str] = set()
    tool_names: set[str] = set()
    for item in report.get("tool_calls", []):
        if not isinstance(item, Mapping):
            continue
        tool = item.get("tool")
        if isinstance(tool, str):
            tool_names.add(tool)
        if tool == "read_source_file" and item.get("status") == "ok":
            args = item.get("arguments", {})
            if isinstance(args, Mapping) and isinstance(args.get("path"), str):
                reads.add(args["path"])
    diagnosis = report.get("diagnosis", {})
    if not isinstance(diagnosis, Mapping):
        diagnosis = {}
    direct_reference_count = 0
    root_cause = diagnosis.get("root_cause", {})
    if isinstance(root_cause, Mapping) and isinstance(root_cause.get("source_references"), list):
        direct_reference_count += len(root_cause["source_references"])
    claims = diagnosis.get("claims", [])
    if isinstance(claims, list):
        for claim in claims:
            if isinstance(claim, Mapping) and isinstance(claim.get("source_references"), list):
                direct_reference_count += len(claim["source_references"])
    return {
        "status": report.get("status", "unknown"),
        "stop_reason": report.get("stop_reason", "unknown"),
        "elapsed_seconds": report.get("elapsed_seconds", 0),
        "model_rounds": budget.get("model_rounds_used", report.get("model_rounds", 0)),
        "tool_call_count": budget.get("tool_calls_used", len(report.get("tool_calls", []))),
        "tool_names": sorted(tool_names),
        "reported_tokens": budget.get("provider_reported_tokens", 0),
        "estimated_cost_usd": budget.get("estimated_cost_usd"),
        "unique_source_read_count": len(reads),
        "source_read_paths": sorted(reads),
        "diagnosis_assurance": report.get("diagnosis_assurance", "not_assessed"),
        "claim_count": len(diagnosis.get("claims", [])) if isinstance(diagnosis.get("claims"), list) else 0,
        "source_reference_count": direct_reference_count,
    }


def _write_checksums(output_dir: Path) -> None:
    rows = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rows.append(f"{_sha256_bytes(path.read_bytes())}  {path.name}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def run_graph_pilot(
    *,
    repo_root: Path,
    output_dir: Path,
    profile_name: str = "ae32c_core",
    provider_name: str = "cloudflare",
    model_name: str = "",
    source_revision: str | None = None,
    runner_revision: str | None = None,
    condition_order: str = "control-first",
    max_cost_usd: float | None = None,
    allow_unpriced_provider_calls: bool = False,
    confirm_live_provider_calls: bool = False,
    profile_path: Path = _DEFAULT_GRAPH_PROFILES,
    provider_profile_path: Path = _DEFAULT_PROVIDER_PROFILES,
) -> dict[str, Any]:
    if not confirm_live_provider_calls:
        raise GraphPilotError("live_provider_calls_require_explicit_confirmation")
    if provider_name not in SUPPORTED_PROVIDERS:
        raise GraphPilotError("unsupported_provider:" + provider_name)
    if model_name and _MODEL_RE.fullmatch(model_name) is None:
        raise GraphPilotError("invalid_model_name")
    if condition_order not in {"control-first", "graph-first"}:
        raise GraphPilotError("invalid_condition_order")

    root = repo_root.expanduser().resolve(strict=True)
    if not root.is_dir() or repo_root.is_symlink():
        raise GraphPilotError("repository_root_unavailable_or_symlinked")
    out = output_dir.expanduser()
    if out.exists() and out.is_symlink():
        raise GraphPilotError("output_directory_must_not_be_symlink")
    out.mkdir(parents=True, exist_ok=True)
    out = out.resolve(strict=True)
    try:
        out.relative_to(root)
    except ValueError:
        pass
    else:
        raise GraphPilotError("output_directory_must_be_outside_repository")

    profile = _load_profile(profile_name, profile_path)
    target = str(profile["graph_target"])
    relation_types = tuple(str(item) for item in profile["graph_relation_types"])
    problem = str(profile.get("problem_statement", "")).strip()
    if not problem:
        raise GraphPilotError("profile_problem_statement_missing")

    run_id = "ae32c-graph-pilot-" + uuid.uuid4().hex
    start_time = time.time()
    with tempfile.TemporaryDirectory(prefix="ae32c-graph-pilot-scope-") as temp_name:
        scope_root = Path(temp_name) / "snapshot"
        scope_manifest = build_scoped_snapshot(root, scope_root, profile)
        evidence_tools = RepositoryEvidenceTools(
            scope_root,
            source_revision=source_revision,
            runner_revision=runner_revision,
        )
        preflight = _graph_preflight(
            evidence_tools,
            target=target,
            relation_types=relation_types,
            depth=profile["graph_query_depth"],
            max_results=profile["graph_query_max_results"],
        )
        graph_provenance = evidence_tools.invoke("repository_summary", {}).get("provenance", {})
        graph_preflight_record = {
            **preflight,
            "scope_manifest_sha256": scope_manifest["manifest_sha256"],
            "source_manifest_sha256": evidence_tools.manifest_sha256,
            "graph_fingerprint": evidence_tools.graph_fingerprint,
            "graph_projection_version": graph_provenance.get("graph_projection_version"),
        }

        model_profile, default_pair_cap = _load_provider_model_profile(provider_name, model_name, provider_profile_path)
        effective_requested_model = model_name
        if max_cost_usd is not None:
            pair_cost_cap = float(max_cost_usd)
        else:
            pair_cost_cap = default_pair_cap
        if not math.isfinite(pair_cost_cap) or not 0 < pair_cost_cap <= 10:
            raise GraphPilotError("pair_cost_cap_must_be_positive_finite_and_at_most_10_usd")

        # Build a provider object before any request to resolve provider defaults.
        # A second independent instance is constructed for the other condition.
        limits_template = build_live_investigation_limits(provider_name, model_name)
        provider_probe = _make_provider(
            provider_name,
            effective_requested_model,
            max_calls=limits_template.max_rounds,
            max_tokens=limits_template.max_tokens_per_call,
        )
        effective_model = _effective_model(provider_probe, effective_requested_model)
        model_profile, _ = _load_provider_model_profile(provider_name, effective_model, provider_profile_path)
        limits_template = _apply_model_runtime_limits(
            limits_template,
            model_profile.get("runtime_limits", {}),
        )
        cost_estimator = _build_cost_estimator(provider_name, effective_model, model_profile)
        if cost_estimator is None and not allow_unpriced_provider_calls:
            raise GraphPilotError(
                "no_cost_profile_for_selected_provider_model; add pricing to provider_model_profiles.json "
                "or pass --allow-unpriced-provider-calls after reviewing provider billing"
            )
        per_condition_cost_cap = pair_cost_cap / 2.0 if cost_estimator is not None else None

        # Do not reuse the probe for a condition; each condition gets an independent provider session.
        del provider_probe
        conditions: dict[str, dict[str, Any]] = {}
        order = ["control", "graph_enabled"] if condition_order == "control-first" else ["graph_enabled", "control"]
        for condition in order:
            graph_enabled = condition == "graph_enabled"
            provider = _make_provider(
                provider_name,
                effective_model,
                max_calls=limits_template.max_rounds,
                max_tokens=limits_template.max_tokens_per_call,
            )
            limits = replace(limits_template, max_cost_usd=per_condition_cost_cap)
            investigator = RepositoryInvestigator(
                scope_root,
                provider,
                provider_name=provider_name,
                model_name=effective_model,
                evidence_tools=evidence_tools,
                enable_graph_tools=graph_enabled,
                require_graph_interaction=graph_enabled,
                required_graph_target=target if graph_enabled else None,
                required_graph_relation_types=relation_types,
                required_graph_min_cross_module_reads=(
                    int(profile["graph_min_cross_module_reads"]) if graph_enabled else 0
                ),
                graph_query_max_depth=(int(profile["graph_query_depth"]) if graph_enabled else None),
                graph_query_max_results=(int(profile["graph_query_max_results"]) if graph_enabled else None),
                limits=limits,
                cost_estimator=cost_estimator,
            )
            condition_started = time.monotonic()
            available_tool_names = sorted(
                item.get("function", {}).get("name")
                for item in investigator._tool_definitions
                if isinstance(item, Mapping)
                and isinstance(item.get("function"), Mapping)
                and isinstance(item.get("function", {}).get("name"), str)
            )
            report = investigator.run(problem)
            report_elapsed = time.monotonic() - condition_started
            conditions[condition] = {
                "graph_tools_enabled": graph_enabled,
                "available_tool_names": available_tool_names,
                "status": report.get("status", "unknown"),
                "summary": _condition_metrics(report),
                "report": report,
                "runner_elapsed_seconds": round(report_elapsed, 3),
            }

        final_summary = evidence_tools.invoke("repository_summary", {}).get("result", {})
        both_snapshot_checks_verified = all(
            conditions[name]["report"].get("snapshot_check_status") == "verified"
            for name in ("control", "graph_enabled")
        )
        source_manifest_stable = (
            evidence_tools.manifest_sha256 == graph_preflight_record["source_manifest_sha256"]
            and both_snapshot_checks_verified
        )
        graph_fingerprint_stable = (
            evidence_tools.graph_fingerprint == graph_preflight_record["graph_fingerprint"]
        )
        if not source_manifest_stable or not graph_fingerprint_stable:
            raise GraphPilotError("source_or_graph_identity_changed_during_paired_run")

        control_paths = set(conditions["control"]["summary"]["source_read_paths"])
        graph_paths = set(conditions["graph_enabled"]["summary"]["source_read_paths"])
        shared_paths = sorted(control_paths & graph_paths)
        control_only = sorted(control_paths - graph_paths)
        graph_only = sorted(graph_paths - control_paths)
        graph_coverage = conditions["graph_enabled"]["report"].get("graph_interaction_coverage", {})
        control_coverage = conditions["control"]["report"].get("graph_interaction_coverage", {})
        graph_tool_names = {"graph_neighbors", "graph_path"}
        control_tools = set(conditions["control"]["available_tool_names"])
        treatment_tools = set(conditions["graph_enabled"]["available_tool_names"])
        non_graph_tools_match = (control_tools - graph_tool_names) == (treatment_tools - graph_tool_names)
        graph_tool_difference_isolated = (
            not (control_tools & graph_tool_names)
            and (treatment_tools & graph_tool_names) == graph_tool_names
            and non_graph_tools_match
        )
        comparison = {
            "schema_version": "ae32c/paired-graph-pilot/v1",
            "evaluation_id": run_id,
            "created_at_unix": round(start_time, 3),
            "provider": provider_name,
            "model": effective_model,
            "runtime_limits": _runtime_limits_record(limits_template),
            "condition_order": order,
            "profile": profile_name,
            "problem_statement": problem,
            "source": {
                "source_revision": source_revision,
                "runner_revision": runner_revision,
                "scope_file_count": scope_manifest["file_count"],
                "scope_total_bytes": scope_manifest["total_bytes"],
                "scope_manifest_sha256": scope_manifest["manifest_sha256"],
                "source_manifest_sha256": evidence_tools.manifest_sha256,
                "graph_fingerprint": evidence_tools.graph_fingerprint,
                "graph_projection_version": graph_provenance.get("graph_projection_version"),
                "indexed_file_count": final_summary.get("indexed_file_count"),
                "graph_node_count": final_summary.get("graph_node_count"),
                "graph_edge_count": final_summary.get("graph_edge_count"),
                "graph_relation_counts": final_summary.get("graph_relation_counts"),
            },
            "design": {
                "control": "same bounded repository snapshot and non-graph evidence tools; graph_neighbors and graph_path are not exposed",
                "treatment": "same bounded repository snapshot and non-graph evidence tools, with graph_neighbors and graph_path exposed and graph interaction required",
                "same_provider_and_model": True,
                "same_problem_statement": True,
                "same_source_snapshot": source_manifest_stable,
                "both_conditions_snapshot_verified": both_snapshot_checks_verified,
                "same_graph_fingerprint": graph_fingerprint_stable,
                "same_limits": True,
                "non_graph_tool_sets_match": non_graph_tools_match,
                "graph_tool_difference_isolated": graph_tool_difference_isolated,
                "control_available_tools": sorted(control_tools),
                "graph_enabled_available_tools": sorted(treatment_tools),
                "intended_intervention": "graph tool availability plus explicit graph-use instruction",
                "required_distinct_cross_module_reads": int(profile["graph_min_cross_module_reads"]),
                "graph_query_policy": {
                    "target": target,
                    "direction": "outgoing",
                    "relation_types": list(relation_types),
                    "max_depth": int(profile["graph_query_depth"]),
                    "max_results": int(profile["graph_query_max_results"]),
                    "treatment_tool_schema_enforced": True,
                },
                "randomization": "single paired pilot; order recorded but no counterbalancing",
            },
            "cost_policy": {
                "pricing_profile_found": cost_estimator is not None,
                "pair_cost_cap_usd": pair_cost_cap,
                "per_condition_cost_cap_usd": per_condition_cost_cap,
                "cost_cap_enforced": cost_estimator is not None,
                "pricing_metadata": getattr(cost_estimator, "pricing_metadata", None),
                "unpriced_provider_calls_explicitly_authorized": bool(allow_unpriced_provider_calls),
                "token_and_elapsed_budgets_remain_enforced": True,
            },
            "conditions": {
                name: {
                    "graph_tools_enabled": item["graph_tools_enabled"],
                    "available_tool_names": item["available_tool_names"],
                    "status": item["status"],
                    "summary": item["summary"],
                    "runner_elapsed_seconds": item["runner_elapsed_seconds"],
                }
                for name, item in conditions.items()
            },
            "comparison": {
                "source_paths": {
                    "control": sorted(control_paths),
                    "graph_enabled": sorted(graph_paths),
                    "shared": shared_paths,
                    "control_only": control_only,
                    "graph_enabled_only": graph_only,
                },
                "graph_interaction": graph_coverage,
                "control_graph_tool_status": control_coverage.get("status"),
                "interpretation": (
                    "This is one matched paired pilot. It can demonstrate graph-tool interaction and describe "
                    "differences in navigation, evidence and resource use. It does not establish causal graph "
                    "benefit or general model/provider performance; repeat with counterbalanced order and "
                    "independent adjudication before making comparative claims."
                ),
            },
            "acceptance": {
                "control_completed": conditions["control"]["status"] in {"completed", "completed_with_incomplete_evidence"},
                "graph_enabled_completed": conditions["graph_enabled"]["status"] in {"completed", "completed_with_incomplete_evidence"},
                "graph_interaction_complete": graph_coverage.get("status") == "complete",
                "graph_tool_difference_isolated": graph_tool_difference_isolated,
                "source_snapshot_stable": source_manifest_stable and graph_fingerprint_stable,
                "diagnostic_accuracy": "not_assessed",
                "human_review_required": True,
            },
        }

        _write_json(out / "scope-manifest.json", scope_manifest)
        _write_json(out / "graph-preflight.json", graph_preflight_record)
        _write_json(out / "control.report.json", conditions["control"]["report"])
        _write_json(out / "graph-enabled.report.json", conditions["graph_enabled"]["report"])
        _write_json(out / "comparison.json", comparison)
        _write_json(out / "review-guide.json", {
            "schema_version": "ae32c/paired-graph-pilot-review-guide/v1",
            "review_landmarks": profile.get("review_landmarks", []),
            "review_questions": [
                "Did each condition identify the same live-evaluation entry point and describe its responsibility accurately?",
                "Did the graph-enabled condition cite actual CALLS observations with correct endpoints and source locations?",
                "Which relevant files were discovered only after graph exploration?",
                "Did the control find the same relationships through ordinary search/read/trace tools?",
                "Were any CALLS edges misleading, ambiguous, or inconsistent with the source?",
                "Did either condition confuse static call relationships with runtime execution?",
                "Which explanation is better supported by exact source evidence, and why?",
            ],
            "scoring_warning": "Do not infer graph benefit from tool usage, token count, response length, or more files read alone.",
        })
        _write_json(out / "run-context.json", {
            "evaluation_id": run_id,
            "provider": provider_name,
            "model": effective_model,
            "source_revision": source_revision,
            "runner_revision": runner_revision,
            "profile": profile_name,
            "graph_target": target,
            "graph_relation_types": list(relation_types),
            "condition_order": order,
            "started_at_unix": round(start_time, 3),
            "finished_at_unix": round(time.time(), 3),
        })
        _write_comparison_markdown(out / "comparison.md", comparison)
        _write_checksums(out)
        return comparison


def _write_comparison_markdown(path: Path, record: Mapping[str, Any]) -> None:
    conditions = record.get("conditions", {})
    control = conditions.get("control", {}).get("summary", {})
    treatment = conditions.get("graph_enabled", {}).get("summary", {})
    comparison = record.get("comparison", {})
    paths = comparison.get("source_paths", {})
    graph = comparison.get("graph_interaction", {})
    lines = [
        "# AE-32C Matched Graph Pilot",
        "",
        f"- Evaluation: `{record.get('evaluation_id')}`",
        f"- Provider/model: `{record.get('provider')}` / `{record.get('model')}`",
        f"- Profile: `{record.get('profile')}`",
        f"- Source manifest: `{record.get('source', {}).get('source_manifest_sha256')}`",
        f"- Graph fingerprint: `{record.get('source', {}).get('graph_fingerprint')}`",
        "",
        "## Paired conditions",
        "",
        "| Metric | Graph-disabled control | Graph-enabled treatment |",
        "|---|---:|---:|",
    ]
    metric_labels = [
        ("status", "Status"),
        ("model_rounds", "Model rounds"),
        ("tool_call_count", "Tool calls"),
        ("reported_tokens", "Reported tokens"),
        ("elapsed_seconds", "Elapsed seconds"),
        ("unique_source_read_count", "Unique source files read"),
        ("source_reference_count", "Source references"),
    ]
    for key, label in metric_labels:
        lines.append(f"| {label} | {control.get(key, 'n/a')} | {treatment.get(key, 'n/a')} |")
    lines.extend([
        "",
        "## Source navigation",
        "",
        f"- Shared read paths: {len(paths.get('shared', []))}",
        f"- Control-only read paths: {len(paths.get('control_only', []))}",
        f"- Graph-enabled-only read paths: {len(paths.get('graph_enabled_only', []))}",
        f"- Graph coverage: `{graph.get('status', 'unknown')}`",
        f"- Graph observations preserved: {graph.get('graph_observation_count', 0)}",
        f"- Verified cross-module reads: {len(graph.get('cross_module_graph_derived_verified_read_paths', []))}",
        f"- Required cross-module reads: {graph.get('required_graph_min_cross_module_reads', 0)}",
        f"- Finalization completion allowance: {comparison.get('runtime_limits', {}).get('finalization_max_tokens_per_call')}",
        "",
        "## Interpretation boundary",
        "",
        str(comparison.get("interpretation", "")),
        "",
        "Diagnostic accuracy is not automatically assessed. Human review is required.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true",
                        help="Required explicit consent for two independent live investigations.")
    parser.add_argument("--repo-root", default=".", help="Repository checkout root.")
    parser.add_argument("--output-dir", required=True, help="Existing or creatable directory outside the checkout.")
    parser.add_argument("--profile", default="ae32c_core", help="Named bounded repository-scope profile.")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS,
                        default=os.environ.get("FEA_LLM_PROVIDER", "cloudflare"))
    parser.add_argument("--model", default=os.environ.get("FEA_LLM_MODEL", ""))
    parser.add_argument("--source-revision", default=os.environ.get("AE32C_SOURCE_REVISION", ""))
    parser.add_argument("--runner-revision", default=os.environ.get("AE32C_RUNNER_REVISION", ""))
    parser.add_argument("--condition-order", choices=("control-first", "graph-first"), default="control-first")
    parser.add_argument("--max-cost-usd", type=float, default=None,
                        help="Maximum estimated cost for the pair, split evenly between conditions when a pricing profile exists.")
    parser.add_argument("--allow-unpriced-provider-calls", action="store_true",
                        help="Explicitly permit a provider/model without a pricing profile; token and time limits still apply, but no dollar cap can be enforced.")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Build the bounded snapshot and verify the target graph query without making provider calls.")
    args = parser.parse_args(argv)

    if args.model and _MODEL_RE.fullmatch(args.model) is None:
        parser.error("--model must be at most 200 characters and use only letters, digits, @, ., _, :, /, or -")
    if args.max_cost_usd is not None and (
        not math.isfinite(args.max_cost_usd) or not 0 < args.max_cost_usd <= 10
    ):
        parser.error("--max-cost-usd must be positive, finite, and no greater than 10")
    if not args.preflight_only and not args.confirm_live_provider_calls:
        parser.error("live provider calls are disabled unless --confirm-live-provider-calls is supplied")

    repo_root = Path(args.repo_root)
    output_dir = Path(args.output_dir)
    try:
        if args.preflight_only:
            root = repo_root.resolve(strict=True)
            out = output_dir.expanduser()
            if out.exists() and out.is_symlink():
                raise GraphPilotError("output_directory_must_not_be_symlink")
            out.mkdir(parents=True, exist_ok=True)
            out = out.resolve(strict=True)
            try:
                out.relative_to(root)
            except ValueError:
                pass
            else:
                raise GraphPilotError("output_directory_must_be_outside_repository")
            profile = _load_profile(args.profile)
            with tempfile.TemporaryDirectory(prefix="ae32c-graph-pilot-preflight-") as temp_name:
                scope_root = Path(temp_name) / "snapshot"
                manifest = build_scoped_snapshot(root, scope_root, profile)
                evidence_tools = RepositoryEvidenceTools(
                    scope_root,
                    source_revision=args.source_revision or None,
                    runner_revision=args.runner_revision or None,
                )
                preflight = _graph_preflight(
                    evidence_tools,
                    target=str(profile["graph_target"]),
                    relation_types=tuple(profile["graph_relation_types"]),
                    depth=profile["graph_query_depth"],
                    max_results=profile["graph_query_max_results"],
                )
                record = {
                    **preflight,
                    "profile": args.profile,
                    "scope_manifest": manifest,
                    "source_manifest_sha256": evidence_tools.manifest_sha256,
                    "graph_fingerprint": evidence_tools.graph_fingerprint,
                    "provider_calls_made": False,
                    "repository_code_executed": False,
                }
                _write_json(out / "preflight.json", record)
                _write_checksums(out)
                print(json.dumps({
                    "preflight_passed": True,
                    "profile": args.profile,
                    "scope_file_count": manifest["file_count"],
                    "scope_total_bytes": manifest["total_bytes"],
                    "graph_fingerprint": evidence_tools.graph_fingerprint,
                    "provider_calls_made": False,
                    "output_dir": str(out),
                }, indent=2, sort_keys=True))
            return 0

        record = run_graph_pilot(
            repo_root=repo_root,
            output_dir=output_dir,
            profile_name=args.profile,
            provider_name=args.provider,
            model_name=args.model,
            source_revision=args.source_revision or None,
            runner_revision=args.runner_revision or None,
            condition_order=args.condition_order,
            max_cost_usd=args.max_cost_usd,
            allow_unpriced_provider_calls=args.allow_unpriced_provider_calls,
            confirm_live_provider_calls=args.confirm_live_provider_calls,
        )
        print(json.dumps({
            "evaluation_id": record["evaluation_id"],
            "provider": record["provider"],
            "model": record["model"],
            "acceptance": record["acceptance"],
            "output_dir": str(output_dir.resolve()),
        }, indent=2, sort_keys=True))
        return 0 if all(record["acceptance"].get(key) is True for key in (
            "control_completed", "graph_enabled_completed", "graph_interaction_complete",
            "graph_tool_difference_isolated", "source_snapshot_stable",
        )) else 2
    except (GraphPilotError, OSError, ValueError, RuntimeError) as exc:
        print(f"AE-32C graph pilot failed safely: {type(exc).__name__}: {str(exc)[:500]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""AE-45 C3 retained-snapshot executor boundary.

This module reconstructs the exact C1/C2 contract and retains the declared-scope
graph for the lifetime of one investigation. It does not construct a provider,
read credentials, or perform network I/O. Provider-factory definitions are only
loaded transitively by the lazy cost-estimator import after validation. The
caller must supply a provider object explicitly to C3ExecutionSession.run();
provider creation and credential access remain an external, separately
authorized operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.ae32c.investigator import (
    InvestigationLimits,
    RepositoryInvestigator,
)
from tools.ae32d_c3_execution_contract import build_c3_execution_contract
from tools.ae32d_deterministic_audit import _git_head
from tools.ae32d_graph_assisted_audit import (
    GRAPH_BACKEND,
    _runner_revision,
    _scope_snapshot,
)

# These are operational safeguards, not additional authority. All
# authorization-controlled fields are copied from the C3 contract.
_FIXED_INVESTIGATOR_LIMITS: dict[str, int] = {
    "max_response_chars": 40_000,
    "max_tool_response_bytes": 100_000,
    "max_tool_context_chars": 10_000,
    "max_total_evidence_bytes": 300_000,
    "max_total_prompt_chars": 350_000,
    "max_snapshot_files": 100,
    "max_snapshot_bytes": 2_000_000,
    "max_invalid_final_attempts": 2,
    "finalization_rounds_reserved": 3,
    "max_invalid_tool_retries": 3,
    "max_invalid_json_retries": 2,
    "max_finalization_invalid_json_retries": 2,
    "max_finalization_recovery_retries": 2,
    "max_provider_transport_retries": 0,
    "finalization_prompt_tokens_reserved_per_round": 1_024,
    "max_source_path_guidance": 2,
}

_GRAPH_SNAPSHOT_FIELDS = (
    "source_revision",
    "source_manifest_sha256",
    "graph_fingerprint",
    "graph_projection_version",
    "evidence_index_status",
    "graph_backend",
    "graph_node_count",
    "graph_edge_count",
    "backend_pipeline_wired",
)


def _graph_snapshot_from_summary(
    source_revision: str, summary_response: Mapping[str, Any]
) -> dict[str, Any]:
    if summary_response.get("status") != "ok":
        raise ValueError("C3_executor_repository_summary_failed")
    provenance = summary_response.get("provenance")
    result = summary_response.get("result")
    if not isinstance(provenance, Mapping) or not isinstance(result, Mapping):
        raise ValueError("C3_executor_repository_summary_shape_invalid")
    runtime = result.get("graph_runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("C3_executor_graph_runtime_missing")
    return {
        "source_revision": source_revision,
        "source_manifest_sha256": provenance.get("source_manifest_sha256"),
        "graph_fingerprint": provenance.get("graph_fingerprint"),
        "graph_projection_version": provenance.get("graph_projection_version"),
        "evidence_index_status": result.get("evidence_index_status"),
        "graph_backend": runtime.get("active_computation_backend", "unknown"),
        "graph_node_count": result.get("graph_node_count", 0),
        "graph_edge_count": result.get("graph_edge_count", 0),
        "backend_pipeline_wired": bool(
            runtime.get("backend_pipeline_wired_into_ae32b_query_path", False)
        ),
    }


def _compare_graph_snapshot(
    observed: Mapping[str, Any], *expected_snapshots: Mapping[str, Any]
) -> None:
    for expected in expected_snapshots:
        for key in _GRAPH_SNAPSHOT_FIELDS:
            if observed.get(key) != expected.get(key):
                raise ValueError("C3_executor_graph_snapshot_mismatch:" + key)
    if observed.get("evidence_index_status") != "complete":
        raise ValueError("C3_executor_graph_index_incomplete")
    if observed.get("backend_pipeline_wired") is not True:
        raise ValueError("C3_executor_graph_backend_not_wired")
    if observed.get("graph_backend") != GRAPH_BACKEND:
        raise ValueError("C3_executor_graph_backend_mismatch")


def _validate_provider_profile(provider: Any, contract: Mapping[str, Any]) -> None:
    """Reject a supplied adapter whose declared identity or local caps differ."""
    expected_provider = contract["provider_name"]
    expected_model = contract["model_name"]
    actual_provider = getattr(provider, "provider_name", None)
    if actual_provider != expected_provider:
        raise ValueError("C3_executor_provider_identity_mismatch")
    models = getattr(provider, "models", None)
    model = getattr(provider, "model", None)
    if isinstance(models, (list, tuple)):
        if list(models) != [expected_model]:
            raise ValueError("C3_executor_provider_model_mismatch")
    elif model != expected_model:
        raise ValueError("C3_executor_provider_model_unverifiable")
    max_calls = getattr(provider, "max_logical_calls", None)
    if (isinstance(max_calls, bool) or not isinstance(max_calls, int)
            or max_calls < 1 or max_calls > contract["investigator_limits"]["max_rounds"]):
        raise ValueError("C3_executor_provider_call_ceiling_mismatch")
    max_tokens = getattr(provider, "max_tokens_per_call", None)
    if (isinstance(max_tokens, bool) or not isinstance(max_tokens, int)
            or max_tokens < 64
            or max_tokens > contract["investigator_limits"]["max_tokens_per_call"]):
        raise ValueError("C3_executor_provider_token_ceiling_mismatch")
    if not callable(getattr(provider, "get_stats", None)):
        raise ValueError("C3_executor_provider_stats_interface_missing")


def _build_investigator_limits(contract_limits: Mapping[str, Any]) -> InvestigationLimits:
    required = {
        "max_rounds",
        "max_tool_calls",
        "max_tokens_per_call",
        "finalization_max_tokens_per_call",
        "max_total_tokens",
        "max_elapsed_seconds",
        "max_cost_usd",
        "temperature",
    }
    if set(contract_limits) != required:
        raise ValueError("C3_executor_contract_limit_fields_mismatch")
    hard_ceilings = {
        "max_rounds": 11,
        "max_tool_calls": 12,
        "max_tokens_per_call": 2_048,
        "finalization_max_tokens_per_call": 6_144,
        "max_total_tokens": 30_720,
        "max_elapsed_seconds": 900,
        "max_cost_usd": 0.50,
    }
    for key, ceiling in hard_ceilings.items():
        value = contract_limits[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 or value > ceiling:
            raise ValueError("C3_executor_authorized_limit_out_of_bounds:" + key)
    temperature = contract_limits["temperature"]
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or temperature != 0.0):
        raise ValueError("C3_executor_temperature_must_be_zero")
    values = dict(_FIXED_INVESTIGATOR_LIMITS)
    values.update(dict(contract_limits))
    limits = InvestigationLimits(**values)
    # Reassert the authorization-controlled values after dataclass validation.
    for key in required:
        if getattr(limits, key) != contract_limits[key]:
            raise ValueError("C3_executor_authorized_limit_changed:" + key)
    return limits


@dataclass
class C3ExecutionSession:
    """One retained graph snapshot and its exact, bounded investigator contract."""

    contract: dict[str, Any]
    source_root: Path
    graph_root: Path
    evidence_tools: RepositoryEvidenceTools
    limits: InvestigationLimits
    cost_estimator: Any
    _temporary_directory: TemporaryDirectory[str] = field(repr=False)
    _investigator: RepositoryInvestigator | None = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def build_investigator(self, provider: Any) -> RepositoryInvestigator:
        """Bind an explicitly supplied provider to the retained, verified graph.

        This method does not create providers, read credentials, or perform
        network I/O. It is intentionally impossible to call without a provider
        object supplied by the caller.
        """
        if self._closed:
            raise RuntimeError("C3_execution_session_closed")
        if self._investigator is not None:
            raise RuntimeError("C3_execution_session_investigator_already_built")
        if provider is None:
            raise ValueError("C3_executor_provider_object_required")
        _validate_provider_profile(provider, self.contract)
        requirements = self.contract["investigation_requirements"]
        self._investigator = RepositoryInvestigator(
            self.graph_root,
            provider,
            provider_name=self.contract["provider_name"],
            model_name=self.contract["model_name"],
            source_revision=self.contract["source_commit_sha"],
            runner_revision=_runner_revision(),
            evidence_tools=self.evidence_tools,
            required_source_paths=tuple(requirements["required_source_paths"]),
            required_context_paths=tuple(requirements["required_context_paths"]),
            required_context_target=requirements["required_context_target"],
            require_complete_investigation_context=True,
            require_graph_interaction=True,
            enable_graph_tools=True,
            required_graph_target=requirements["required_graph_target"],
            required_graph_relation_types=tuple(
                requirements["required_graph_relation_types"]
            ),
            required_graph_direction=requirements["required_graph_direction"],
            prefetch_required_graph_query=True,
            prefetch_required_context_trace=True,
            limits=self.limits,
            cost_estimator=self.cost_estimator,
        )
        return self._investigator

    def run(self, provider: Any) -> dict[str, Any]:
        """Run once with a caller-supplied provider, then verify snapshot identity."""
        if _git_head(self.source_root) != self.contract["source_commit_sha"]:
            raise ValueError("C3_executor_source_revision_changed_before_run")
        investigator = self.build_investigator(provider)
        report = investigator.run(self.contract["investigator_problem"])
        if _git_head(self.source_root) != self.contract["source_commit_sha"]:
            raise ValueError("C3_executor_source_revision_changed_during_run")
        provenance = report.get("provenance", {})
        if not isinstance(provenance, Mapping):
            raise ValueError("C3_executor_report_provenance_missing")
        expected = {
            "source_revision": self.contract["source_commit_sha"],
            "source_manifest_sha256": self.contract["source_manifest_sha256"],
            "graph_fingerprint": self.contract["graph_fingerprint"],
        }
        for key, value in expected.items():
            if provenance.get(key) != value:
                raise ValueError("C3_executor_report_provenance_mismatch:" + key)
        if report.get("snapshot_check_status") != "verified":
            raise ValueError("C3_executor_investigator_snapshot_not_verified")
        return report

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.evidence_tools.close()
        finally:
            self._temporary_directory.cleanup()

    def __enter__(self) -> "C3ExecutionSession":
        if self._closed:
            raise RuntimeError("C3_execution_session_closed")
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def prepare_c3_execution(
    task_projection: dict[str, Any],
    b_report: dict[str, Any],
    request_package: dict[str, Any],
    c_snapshot_verification: dict[str, Any],
    authorization: dict[str, Any],
    source_root: str | Path,
    *,
    manual_dispatch_confirmed: bool = False,
) -> C3ExecutionSession:
    """Validate C0/C1/C2, rebuild and retain the exact graph, and prepare limits.

    No provider factory is called and no provider is constructed. The cost
    estimator is loaded lazily after validation; its current module imports
    provider-factory definitions but does not invoke them. A caller-supplied
    provider is required only if/when the session is explicitly invoked.
    """
    contract = build_c3_execution_contract(
        task_projection,
        b_report,
        request_package,
        c_snapshot_verification,
        authorization,
        manual_dispatch_confirmed=manual_dispatch_confirmed,
    )
    if contract.get("status") != "ready_for_c3_executor":
        raise ValueError("C3_executor_contract_not_authorized:" + str(contract.get("status")))

    root = Path(source_root).expanduser().resolve(strict=True)
    source_revision = _git_head(root)
    if source_revision != contract.get("source_commit_sha"):
        raise ValueError("C3_executor_checkout_revision_mismatch")
    if b_report.get("source_commit_sha") != source_revision:
        raise ValueError("C3_executor_B_source_revision_mismatch")

    temporary = TemporaryDirectory(prefix="ae32d-c3-retained-")
    evidence_tools: RepositoryEvidenceTools | None = None
    try:
        graph_root = Path(temporary.name)
        scope_snapshot = _scope_snapshot(task_projection, root, graph_root)
        expected_manifest = b_report["baseline_report"]["source_manifest_digest"]
        if scope_snapshot.get("issues") or scope_snapshot.get("digest") != expected_manifest:
            raise ValueError("C3_executor_declared_scope_manifest_mismatch")

        evidence_tools = RepositoryEvidenceTools(
            graph_root,
            source_revision=source_revision,
            runner_revision=_runner_revision(),
            graph_backend=GRAPH_BACKEND,
        )
        summary_response = evidence_tools.invoke("repository_summary", {})
        observed = _graph_snapshot_from_summary(source_revision, summary_response)
        _compare_graph_snapshot(
            observed,
            b_report["graph_snapshot"],
            c_snapshot_verification["expected_graph_snapshot"],
            c_snapshot_verification["observed_graph_snapshot"],
        )
        if _git_head(root) != source_revision:
            raise ValueError("C3_executor_source_revision_changed_during_rebuild")

        required_paths = (
            list(contract["investigation_requirements"]["required_source_paths"])
            + list(contract["investigation_requirements"]["required_context_paths"])
            + [contract["investigation_requirements"]["required_context_target"]]
        )
        missing = sorted({path for path in required_paths if path not in evidence_tools.file_hashes})
        if missing:
            raise ValueError("C3_executor_required_paths_not_indexed:" + ",".join(missing))

        # Import the pricing estimator only after C0/C1/C2, checkout, scope and
        # retained graph checks have succeeded. The module import is not a
        # provider construction or credential access.
        from audit_engine.semantic_audit.ae32c.live_evaluation import (
            build_live_cost_estimator,
        )

        cost_estimator = build_live_cost_estimator(
            contract["provider_name"], contract["model_name"]
        )
        if cost_estimator is None:
            raise ValueError("C3_executor_cost_estimator_unavailable")
        limits = _build_investigator_limits(contract["investigator_limits"])
        contract = dict(contract)
        contract["source_manifest_sha256"] = observed["source_manifest_sha256"]
        contract["investigator_problem"] = request_package["request"]["investigator_problem"]
        return C3ExecutionSession(
            contract=contract,
            source_root=root,
            graph_root=graph_root,
            evidence_tools=evidence_tools,
            limits=limits,
            cost_estimator=cost_estimator,
            _temporary_directory=temporary,
        )
    except Exception:
        if evidence_tools is not None:
            evidence_tools.close()
        temporary.cleanup()
        raise

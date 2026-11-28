"""End-to-end C3 session integration on the pinned, immutable case fixture.

This composes real B, C1, C2, retained C3 reconstruction, and the investigator
run wrapper. The only provider is an in-process deterministic fake; no
credentials, provider factory, network transport, or live dispatch are used.
"""
from __future__ import annotations

from tests.semantic_audit.test_ae32c_investigator import (
    FakeProvider,
    action_tool,
    final_action,
)
from tests.semantic_audit.test_ae32d_c_request import (
    CASE_SHA,
    build_auth,
    case_record,
    pinned_root,
)
from tools.ae32d_c3_executor import prepare_c3_execution
from tools.ae32d_c_preflight import build_c_preflight
from tools.ae32d_c_request import build_c_request_package
from tools.ae32d_c_snapshot import verify_c_graph_snapshot
from tools.ae32d_graph_assisted_audit import run_graph_assisted_audit
from tools.ae32d_trial_contracts import build_sanitized_task_projection


MODEL = "@cf/qwen/qwen3.8-27b"


class CloudflareDeterministicFakeProvider(FakeProvider):
    """Fake with the exact declared profile and a fresh zero-usage boundary."""

    provider_name = "cloudflare"
    model = MODEL
    models = [MODEL]
    max_logical_calls = 11
    max_tokens_per_call = 2_048

    def get_stats(self):
        return {
            "provider": self.provider_name,
            "model": self.model,
            "logical_calls": 0,
            "total_calls": 0,
            "http_attempts": 0,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "reported_cost_usd": 0.0,
            },
        }


def test_real_c1_c2_retained_c3_session_enforces_budget_and_cleanup():
    root = pinned_root()
    record = case_record()
    record["task"]["title"] = "C3 end-to-end"
    record["task"]["problem_statement"] = "Inspect the declared source and graph evidence."
    record["task"]["declared_scope"] = ["control.py", "expected_behavior.json"]
    b_projection = build_sanitized_task_projection(
        record, experiment_id="AE45-C3-E2E", condition="B_graph"
    )
    c_projection = build_sanitized_task_projection(
        record, experiment_id="AE45-C3-E2E", condition="C_graph_llm"
    )

    # Rebuild the real B evidence and C1 authorization package from the pinned
    # source fixture rather than using synthetic digests or patched contracts.
    b_report = run_graph_assisted_audit(b_projection, root)
    # Keep the actual B graph snapshot and the two retrieval records required
    # by C0, but bound the context passed into C1 to one graph-neighbor result.
    # This is a derived request-context view; it does not alter the pinned source
    # or the graph snapshot that C2/C3 independently reconstruct.
    summary_record = next(
        item for item in b_report["graph_retrieval"]
        if item["tool"] == "repository_summary" and item["status"] == "ok"
    )
    neighbor_record = next(
        item for item in b_report["graph_retrieval"]
        if item["tool"] == "graph_neighbors"
        and item["status"] == "ok"
        and item["payload"].get("discovered_nodes")
    )
    neighbor_record = dict(neighbor_record)
    neighbor_record["payload"] = dict(neighbor_record["payload"])
    neighbor_record["payload"]["discovered_nodes"] = neighbor_record["payload"]["discovered_nodes"][:1]
    summary_record = dict(summary_record)
    summary_record["payload"] = {}
    neighbor_record["payload"] = {
        "discovered_nodes": neighbor_record["payload"]["discovered_nodes"][:1]
    }
    b_report["graph_retrieval"] = [summary_record, neighbor_record]
    for key in ("findings", "counterevidence", "unresolved_questions", "limitations"):
        bounded = b_report["baseline_report"][key][:1]
        b_report["baseline_report"][key] = bounded
        b_report[key] = bounded
    preflight = build_c_preflight(b_report)
    authorization = build_auth(preflight)
    # Use the full permitted deterministic-test envelope: the smaller generic
    # C1 fixture budget cannot reserve the mandatory finalization tokens after
    # the complete B/C context is prefetched. This authorization is test-only;
    # the provider below is an in-process fake and cannot dispatch externally.
    authorization.update(
        max_model_rounds=11,
        max_tool_calls=12,
        max_tokens_per_call=512,
        finalization_max_tokens_per_call=4_096,
        max_total_tokens=30_720,
        max_elapsed_seconds=900,
        max_cost_usd=0.50,
    )
    request_package = build_c_request_package(
        c_projection, b_report, authorization
    )
    assert request_package["status"] == "prepared_manual_only"

    # C2 independently reconstructs the graph and closes its own temporary
    # evidence-tools instance before the C3 executor creates its retained copy.
    c2_report = verify_c_graph_snapshot(c_projection, b_report, root)
    assert c2_report["status"] == "verified"
    assert all(
        c2_report["observed_graph_snapshot"][key] == value
        for key, value in c2_report["expected_graph_snapshot"].items()
        if key != "status"
    )

    # This confirmation is confined to a deterministic test using an injected
    # fake. It does not authorize or perform any live provider dispatch.
    provider = CloudflareDeterministicFakeProvider([
        action_tool("read_source_file", {
            "path": "control.py", "start_line": 1, "end_line": 5,
        }),
        action_tool("read_source_file", {
            "path": "expected_behavior.json", "start_line": 1, "end_line": 24,
        }),
        final_action(
            evidence_id="E0002",
            source_reference=False,
            summary="The pinned source and expected-behavior evidence were inspected.",
            claim_statement="The retained C3 evidence supports a bounded static observation.",
        ),
    ])
    provider.max_logical_calls = authorization["max_model_rounds"]
    provider.max_tokens_per_call = authorization["max_tokens_per_call"]

    with prepare_c3_execution(
        c_projection,
        b_report,
        request_package,
        c2_report,
        authorization,
        root,
        manual_dispatch_confirmed=True,
    ) as session:
        assert session.contract["source_commit_sha"] == CASE_SHA
        assert session.evidence_tools.manifest_sha256 == b_report["graph_snapshot"]["source_manifest_sha256"]
        assert session.evidence_tools.graph_fingerprint == b_report["graph_snapshot"]["graph_fingerprint"]
        assert session.limits.max_rounds == authorization["max_model_rounds"]
        assert session.limits.max_tool_calls == authorization["max_tool_calls"]
        assert session.limits.finalization_max_tokens_per_call == authorization["finalization_max_tokens_per_call"]
        assert session.limits.max_total_tokens == authorization["max_total_tokens"]
        assert session.limits.max_elapsed_seconds == authorization["max_elapsed_seconds"]
        assert session.limits.max_cost_usd == authorization["max_cost_usd"]

        report = session.run(provider)

        # Compact C1 orientation plus bounded model-facing evidence views allow
        # the fake investigation to finish inside the same authorized ceiling.
        assert report["status"] == "completed", {
            "stop_reason": report.get("stop_reason"),
            "errors": report.get("errors"),
            "provider_calls": provider.calls,
            "budget": report.get("budget"),
        }
        assert report["diagnosis"] is not None
        assert report["snapshot_check_status"] == "verified"
        assert report["provenance"]["source_revision"] == CASE_SHA
        assert report["provenance"]["source_manifest_sha256"] == session.contract["source_manifest_sha256"]
        assert report["provenance"]["graph_fingerprint"] == session.contract["graph_fingerprint"]
        assert report["budget"]["max_rounds"] == authorization["max_model_rounds"]
        assert report["budget"]["max_tool_calls"] == authorization["max_tool_calls"]
        assert report["budget"]["max_total_tokens"] == authorization["max_total_tokens"]
        assert report["budget"]["reserved_token_estimate"] <= authorization["max_total_tokens"]
        assert provider.calls == 3
        assert any(item["tool"] == "repository_summary" for item in report["tool_calls"])
        assert any(item["tool"] == "read_source_file" for item in report["tool_calls"])
        assert any(item["tool"] == "trace_execution_context" for item in report["tool_calls"])
        assert any(item["tool"] == "graph_neighbors" for item in report["tool_calls"])


    assert session._closed is True

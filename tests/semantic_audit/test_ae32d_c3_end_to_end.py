"""End-to-end C3 integration over an isolated, committed two-module source fixture.

This composes real B, C1, C2, retained C3 reconstruction, graph follow-through,
and the investigator run wrapper. The only provider is an in-process fake.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from tests.semantic_audit.test_ae32c_investigator import (
    FakeProvider,
    action_tool,
)
from tests.semantic_audit.test_ae32d_c_request import (
    build_auth,
    case_record,
)
from audit_engine.semantic_audit.ae32c.investigator import _source_reference_candidate_id
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


def _make_isolated_source(root: Path) -> str:
    """Create a tiny, committed two-module graph with one cross-module call."""
    fixture = root / "src"
    fixture.mkdir()
    (fixture / "control.py").write_text(
        "from helper import normalize\n\n"
        "def work(flag):\n"
        "    return normalize(flag)\n",
        encoding="utf-8",
    )
    (fixture / "helper.py").write_text(
        "def normalize(flag):\n"
        "    return 5 if flag else 0\n",
        encoding="utf-8",
    )
    (fixture / "expected_behavior.json").write_text(
        json.dumps({
            "schema_version": "ae32d/expected-behavior/v1",
            "function": "work",
            "input_cases": [
                {"arguments": [True], "expected": {"kind": "return", "value": 5}},
                {"arguments": [False], "expected": {"kind": "return", "value": 0}},
            ],
        }, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "C3 Integration Fixture"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "c3-fixture@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "add", "src/control.py", "src/helper.py", "src/expected_behavior.json"], cwd=root, check=True)
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    })
    subprocess.run(
        ["git", "commit", "-q", "-m", "Create deterministic C3 integration fixture"],
        cwd=root, env=env, check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _final_action_with_required_source_refs(root: Path) -> str:
    source_records = (
        ("E0003", "control.py"),
        ("E0004", "expected_behavior.json"),
        ("E0005", "helper.py"),
    )
    references = []
    evidence_ids = []
    for evidence_id, path in source_records:
        source_hash = __import__("hashlib").sha256(
            (root / "src" / path).read_bytes()
        ).hexdigest()
        references.append({
            "candidate_id": _source_reference_candidate_id({
                "evidence_id": evidence_id,
                "path": path,
                "line": 1,
                "source_sha256": source_hash,
            })
        })
        evidence_ids.append(evidence_id)
    return json.dumps({
        "action": "final",
        "diagnosis": {
            "summary": "The graph and direct source evidence establish a cross-module delegation.",
            "root_cause": {
                "statement": "control.work delegates to helper.normalize through the statically resolved import call.",
                "confidence": "high",
                "evidence_refs": evidence_ids,
                "source_references": references,
            },
            "claims": [{
                "statement": "The CALLS graph edge from control.work resolves to helper.normalize, and both source files were directly inspected.",
                "kind": "static_inference",
                "confidence": "high",
                "evidence_refs": evidence_ids,
                "source_references": references,
            }],
            "proposed_corrective_action": "No source correction is indicated by this bounded fixture; preserve the explicit helper delegation.",
            "limitations": ["Static graph and source evidence do not establish runtime execution."],
            "next_steps": ["Validate runtime behavior separately if an execution claim is required."],
        },
    })


def test_real_c1_c2_retained_c3_session_completes_within_budget():
    with tempfile.TemporaryDirectory(prefix="ae45-c3-e2e-") as directory:
        root = Path(directory)
        source_sha = _make_isolated_source(root)
        record = case_record()
        record["source"]["source_commit_sha"] = source_sha
        record["source"]["fixture_path"] = "src"
        record["task"]["title"] = "C3 end-to-end graph follow-through"
        record["task"]["problem_statement"] = (
            "Inspect the declared source and determine whether work delegates "
            "its behavior through the imported helper."
        )
        record["task"]["declared_scope"] = [
            "control.py", "helper.py", "expected_behavior.json"
        ]
        b_projection = build_sanitized_task_projection(
            record, experiment_id="AE45-C3-E2E", condition="B_graph"
        )
        c_projection = build_sanitized_task_projection(
            record, experiment_id="AE45-C3-E2E", condition="C_graph_llm"
        )

        # Rebuild B from the isolated committed source, not synthetic graph data.
        b_report = run_graph_assisted_audit(b_projection, root)
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
        summary_record = dict(summary_record)
        summary_record["payload"] = {}
        neighbor_record = dict(neighbor_record)
        neighbor_record["payload"] = {
            "discovered_nodes": neighbor_record["payload"]["discovered_nodes"][:2],
            "source_paths": neighbor_record["payload"].get("source_paths", [])[:4],
            "observed_relation_types": neighbor_record["payload"].get("observed_relation_types", [])[:6],
        }
        b_report["graph_retrieval"] = [summary_record, neighbor_record]
        for key in ("findings", "counterevidence", "unresolved_questions", "limitations"):
            bounded = b_report["baseline_report"][key][:1]
            b_report["baseline_report"][key] = bounded
            b_report[key] = bounded

        preflight = build_c_preflight(b_report)
        authorization = build_auth(preflight)
        # Tight test-only per-call caps. The overall authorization ceiling and
        # three-round finalization reserve remain unchanged.
        authorization.update(
            max_model_rounds=11,
            max_tool_calls=12,
            max_tokens_per_call=512,
            finalization_max_tokens_per_call=1_536,
            max_total_tokens=30_720,
            max_elapsed_seconds=900,
            max_cost_usd=0.50,
        )
        request_package = build_c_request_package(
            c_projection, b_report, authorization
        )
        assert request_package["status"] == "prepared_manual_only"
        assert len(request_package["request"]["investigator_problem"]) < 5_000

        # C2 independently reconstructs the exact graph over the committed fixture.
        c2_report = verify_c_graph_snapshot(c_projection, b_report, root)
        assert c2_report["status"] == "verified"
        assert all(
            c2_report["observed_graph_snapshot"][key] == value
            for key, value in c2_report["expected_graph_snapshot"].items()
            if key != "status"
        )

        provider = CloudflareDeterministicFakeProvider([
            # This is the cross-module path surfaced by the required graph query.
            action_tool("read_source_file", {
                "path": "helper.py", "start_line": 1, "end_line": 2,
            }),
            action_tool("read_source_file", {
                "path": "expected_behavior.json", "start_line": 1, "end_line": 40,
            }),
            _final_action_with_required_source_refs(root),
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
            assert session.contract["source_commit_sha"] == source_sha
            assert session.evidence_tools.manifest_sha256 == b_report["graph_snapshot"]["source_manifest_sha256"]
            assert session.evidence_tools.graph_fingerprint == b_report["graph_snapshot"]["graph_fingerprint"]
            assert session.limits.max_rounds == authorization["max_model_rounds"]
            assert session.limits.max_tool_calls == authorization["max_tool_calls"]
            assert session.limits.finalization_max_tokens_per_call == authorization["finalization_max_tokens_per_call"]
            assert session.limits.max_total_tokens == authorization["max_total_tokens"]
            assert session.limits.max_elapsed_seconds == authorization["max_elapsed_seconds"]
            assert session.limits.max_cost_usd == authorization["max_cost_usd"]
            report = session.run(provider)
            tool_catalog = session._investigator._tool_catalog_for_prompt()
            assert len(json.dumps(tool_catalog, sort_keys=True)) < 20_000
            assert {item["name"] for item in tool_catalog} >= {
                "read_source_file", "graph_neighbors", "graph_path",
                "trace_execution_context", "find_related_tests", "discover_case_context",
            }

            assert report["status"] == "completed", {
                "stop_reason": report.get("stop_reason"),
                "errors": report.get("errors"),
                "provider_calls": provider.calls,
                "budget": report.get("budget"),
            }
            assert report["diagnosis"] is not None
            assert report["snapshot_check_status"] == "verified"
            assert report["provenance"]["source_revision"] == source_sha
            assert report["provenance"]["source_manifest_sha256"] == session.contract["source_manifest_sha256"]
            assert report["provenance"]["graph_fingerprint"] == session.contract["graph_fingerprint"]
            assert report["budget"]["max_rounds"] == authorization["max_model_rounds"]
            assert report["budget"]["max_tool_calls"] == authorization["max_tool_calls"]
            assert report["budget"]["max_total_tokens"] == authorization["max_total_tokens"]
            assert report["budget"]["reserved_token_estimate"] <= authorization["max_total_tokens"]
            source_coverage = report["required_source_coverage"]
            assert source_coverage["status"] == "complete"
            assert set(source_coverage["root_cause_direct_citation_paths"]) == {
                "control.py", "helper.py", "expected_behavior.json"
            }
            assert provider.calls == 3
            assert any(item["tool"] == "repository_summary" for item in report["tool_calls"])
            assert any(item["tool"] == "read_source_file" for item in report["tool_calls"])
            assert any(item["tool"] == "trace_execution_context" for item in report["tool_calls"])
            assert any(item["tool"] == "find_related_tests" for item in report["tool_calls"])
            assert any(item["tool"] == "discover_case_context" for item in report["tool_calls"])
            assert any(item["tool"] == "graph_neighbors" for item in report["tool_calls"])
            graph_coverage = report["graph_interaction_coverage"]
            context_coverage = report["investigation_context_coverage"]
            assert context_coverage["status"] == "complete_for_available_static_context"
            context_contract = context_coverage["required_context_contract"]
            assert context_contract["status"] == "complete"
            expected_behavior_path = next(
                item for item in context_contract["required_paths"]
                if item["path"] == "expected_behavior.json"
            )
            assert expected_behavior_path["read"] is True
            assert expected_behavior_path["surfaced"] is False
            assert expected_behavior_path["status"] == "read_not_surfaced"
            assert graph_coverage["graph_follow_through_complete"] is True
            assert "helper.py" in graph_coverage["cross_module_graph_source_paths"]
            assert any(
                query["target"] == "control.py"
                and query["initiator"] == "orchestrator_prefetch"
                and "helper.py" in query["source_paths"]
                for query in graph_coverage["graph_queries"]
            )
            assert "helper.py" in graph_coverage["cross_module_graph_derived_verified_read_paths"]

        assert session._closed is True

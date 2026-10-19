"""Deterministic end-to-end contract tests for the AE-32C incident evaluation.

The provider is fake, but the repository evidence tools and graph are real. No
fixture code is executed and no live provider credentials are required.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.ae32c.evaluation import (
    build_comparison_record,
    render_comparison_markdown,
    summarize_graph_report,
)
from audit_engine.semantic_audit.ae32c.investigator import InvestigationLimits, RepositoryInvestigator
from audit_engine.semantic_audit.ae32c.live_evaluation import main as live_evaluation_main


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ae32c_provider_interface_incident"
PROBLEM = (
    "A previous extraction workflow failed with AttributeError because the "
    "consumer attempted to access provider.total_calls. Investigate available "
    "source, test, graph, and workflow evidence without assuming a correction."
)


class ScriptedProvider:
    provider_name = "deterministic-test-provider"
    model = "deterministic-test-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reported_cost_usd": 0.0}

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.messages.append([dict(item) for item in messages])
        self.usage["prompt_tokens"] += 80
        self.usage["completion_tokens"] += 50
        self.usage["total_tokens"] += 130
        if not self.responses:
            return None, "scripted response queue exhausted"
        return self.responses.pop(0), None

    def get_stats(self):
        return {"provider": self.provider_name, "model": self.model, "usage": dict(self.usage)}


def _tool_action(tool, arguments, reason):
    return json.dumps({"action": "tool_call", "tool": tool, "arguments": arguments, "reason": reason})


def _final_action(source_hash):
    source_ref = {
        "evidence_id": "E0002",
        "path": "pipeline/extractor.py",
        "line": 6,
        "source_sha256": source_hash,
    }
    # The scripted conclusion is only a contract fixture. It does not claim
    # that the real incident was diagnosed by a live LLM.
    return json.dumps({
        "action": "final",
        "diagnosis": {
            "summary": "The source evidence indicates a provider-interface mismatch; runtime causality is not independently proven.",
            "root_cause": {
                "statement": "The consumer requests total_calls while the inspected adapter exposes a differently named counter.",
                "confidence": "medium",
                "evidence_refs": ["E0002", "E0003"],
                "source_references": [source_ref],
            },
            "claims": [{
                "statement": "The retrieved source line contains the total_calls access.",
                "kind": "observation",
                "confidence": "high",
                "evidence_refs": ["E0002"],
                "source_references": [source_ref],
            }],
            "proposed_corrective_action": "Review the consumer and adapter contract, then add a focused compatibility test before proposing a correction.",
            "limitations": ["The fixture was not executed; static evidence does not establish runtime behavior."],
            "next_steps": ["Review the related test source and workflow entrypoint."],
        },
    })


def test_controlled_incident_drives_real_evidence_tools_over_multiple_rounds():
    tools = RepositoryEvidenceTools(FIXTURE_ROOT)
    source_hash = tools.file_hashes["pipeline/extractor.py"]
    provider = ScriptedProvider([
        _tool_action("search_repository", {"query": "total_calls", "mode": "content", "max_results": 20}, "Locate the consumer's interface access."),
        _tool_action("read_source_file", {"path": "providers/adapter.py", "start_line": 1}, "Inspect the adapter's actual counter interface."),
        _tool_action("find_related_tests", {"target": "pipeline/extractor.py", "max_results": 10}, "Find tests that refer to the consumer."),
        _tool_action("graph_path", {"source": "module:pipeline.extractor", "target": "module:providers.adapter", "max_depth": 4}, "Check the static dependency path."),
        _tool_action("find_workflow_context", {"target": "main.py", "max_results": 10}, "Find workflow context for the entrypoint."),
        _final_action(source_hash),
    ])
    investigator = RepositoryInvestigator(
        FIXTURE_ROOT,
        provider,
        provider_name=provider.provider_name,
        model_name=provider.model,
        evidence_tools=tools,
        limits=InvestigationLimits(
            max_rounds=6,
            max_tool_calls=7,
            max_tokens_per_call=500,
            max_total_tokens=32_000,
            max_elapsed_seconds=120,
            max_snapshot_files=100,
            max_snapshot_bytes=2_000_000,
        ),
        id_factory=lambda: "ae32c-controlled-incident-test",
    )

    report = investigator.run(PROBLEM)

    assert report["status"] in {"completed", "completed_with_incomplete_evidence"}, (
        f"stop_reason={report.get('stop_reason')!r}; "
        f"budget={report.get('budget')!r}; "
        f"errors={report.get('errors')!r}"
    )
    assert report["stop_reason"] in {
        "diagnosis_submitted",
        "diagnosis_submitted_with_coverage_or_snapshot_limitations",
    }, (
        f"expected final diagnosis action; got stop_reason={report.get('stop_reason')!r}; "
        f"errors={report.get('errors')!r}"
    )
    assert report["diagnosis_assurance"] == "references_resolved_not_independently_proven"
    assert report["diagnosis"]["root_cause"]["source_references"][0] == {
        "evidence_id": "E0002",
        "path": "pipeline/extractor.py",
        "line": 6,
        "source_sha256": source_hash,
    }
    assert [item["tool"] for item in report["tool_calls"]] == [
        "repository_summary",
        "search_repository",
        "read_source_file",
        "find_related_tests",
        "graph_path",
        "find_workflow_context",
    ]
    assert len(provider.messages) == 6
    assert all(item["status"] == "ok" for item in report["tool_calls"])
    assert report["evidence_ledger"][1]["evidence_id"] == "E0002"
    assert "E0002" in provider.messages[1][-1]["content"]
    assert "E0005" in provider.messages[4][-1]["content"]
    assert "references_resolved_not_independently_proven" == report["diagnosis_assurance"]


def test_comparison_metrics_describe_behavior_without_claiming_accuracy():
    graph_report = {
        "status": "completed_with_incomplete_evidence",
        "stop_reason": "diagnosis_submitted_with_coverage_or_snapshot_limitations",
        "diagnosis_assurance": "references_resolved_not_independently_proven",
        "budget": {"model_rounds_used": 3},
        "tool_calls": [{"tool": "repository_summary"}, {"tool": "search_repository"}],
        "evidence_ledger": [{"evidence_id": "E0001"}, {"evidence_id": "E0002"}],
        "model_actions": [{"action": "final_accepted", "citation_validation": "references_resolved"}],
        "diagnosis": {"root_cause": {"source_references": [{"evidence_id": "E0002"}]}, "claims": []},
    }
    summary = summarize_graph_report(graph_report)
    assert summary["tool_call_count"] == 2
    record = build_comparison_record(
        problem_statement=PROBLEM,
        provider_name="test-provider",
        model_name="test-model",
        source_manifest_sha256="a" * 64,
        baseline_status="completed",
        baseline_response="Limited-context hypothesis.",
        baseline_error=None,
        baseline_source_path="pipeline/extractor.py",
        baseline_source_sha256="b" * 64,
        graph_report=graph_report,
    )

    assert record["comparison_metrics"]["graph_assisted_tool_call_count"] == 2
    assert record["comparison_metrics"]["graph_assisted_source_reference_count"] == 1
    assert record["evaluation_policy"]["diagnostic_accuracy"] == "not_automatically_assessed"
    assert record["evaluation_policy"]["graph_benefit"] == "not_claimed_without_independent_comparison"
    assert record["evaluation_policy"]["human_review_required"] is True
    markdown = render_comparison_markdown(record)
    assert "Human review is required" in markdown
    assert "not assessed" in markdown.lower()


def test_comparison_record_rejects_malformed_manifest_hash():
    with pytest.raises(ValueError, match="source_manifest_sha256"):
        build_comparison_record(
            problem_statement=PROBLEM,
            provider_name="test-provider",
            model_name="test-model",
            source_manifest_sha256="not-a-hash",
            baseline_status="not_run",
            baseline_response=None,
            baseline_error=None,
            baseline_source_path="pipeline/extractor.py",
            baseline_source_sha256=None,
            graph_report=None,
        )


def test_live_evaluation_requires_explicit_opt_in_before_any_provider_call(tmp_path: Path):
    # The parser must stop before provider construction unless the user opts in.
    with pytest.raises(SystemExit):
        live_evaluation_main([
            "--repo-root", str(FIXTURE_ROOT),
            "--output-dir", str(tmp_path),
            "--problem", "controlled test only",
        ])


def test_fixture_is_controlled_and_contains_no_prescribed_patch():
    consumer = (FIXTURE_ROOT / "pipeline" / "extractor.py").read_text(encoding="utf-8")
    adapter = (FIXTURE_ROOT / "providers" / "adapter.py").read_text(encoding="utf-8")
    incident = json.loads((FIXTURE_ROOT / "incident.json").read_text(encoding="utf-8"))
    assert "provider.total_calls" in consumer
    assert "self.calls" in adapter
    assert "self.total_calls" not in adapter
    assert incident["case_id"] == "AE32C-HIST-PROVIDER-COUNTER-01"
    assert hashlib.sha256((FIXTURE_ROOT / "pipeline" / "extractor.py").read_bytes()).hexdigest()


def test_comparison_artifacts_are_published_as_a_unique_hashed_bundle(tmp_path: Path):
    from audit_engine.semantic_audit.ae32c.evaluation import write_comparison_artifacts

    checkout = tmp_path / "checkout"
    output = tmp_path / "external-output"
    checkout.mkdir()
    output.mkdir()
    record = build_comparison_record(
        problem_statement=PROBLEM,
        provider_name="test-provider",
        model_name="test-model",
        source_manifest_sha256="a" * 64,
        baseline_status="completed",
        baseline_response="baseline result",
        baseline_error=None,
        baseline_source_path="pipeline/extractor.py",
        baseline_source_sha256="b" * 64,
        graph_report={"status": "incomplete", "stop_reason": "test", "tool_calls": [], "evidence_ledger": [], "model_actions": []},
    )
    published = write_comparison_artifacts(record, output_dir=output, checkout_root=checkout)
    directory = Path(published["directory"])
    assert published["publication"] == "atomic_directory_rename"
    assert (directory / "comparison.json").is_file()
    assert (directory / "comparison.md").is_file()
    assert (directory / "SHA256SUMS.txt").is_file()
    manifest = (directory / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert hashlib.sha256((directory / "comparison.json").read_bytes()).hexdigest() in manifest
    assert hashlib.sha256((directory / "comparison.md").read_bytes()).hexdigest() in manifest


def test_comparison_artifact_writer_rejects_output_inside_checkout(tmp_path: Path):
    from audit_engine.semantic_audit.ae32c.evaluation import write_comparison_artifacts

    checkout = tmp_path / "checkout"
    output = checkout / "reports"
    output.mkdir(parents=True)
    record = build_comparison_record(
        problem_statement=PROBLEM,
        provider_name="test-provider",
        model_name="test-model",
        source_manifest_sha256="a" * 64,
        baseline_status="not_run",
        baseline_response=None,
        baseline_error=None,
        baseline_source_path="pipeline/extractor.py",
        baseline_source_sha256=None,
        graph_report=None,
    )
    with pytest.raises(ValueError, match="outside_checkout"):
        write_comparison_artifacts(record, output_dir=output, checkout_root=checkout)

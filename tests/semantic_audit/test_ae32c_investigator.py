"""Deterministic tests for the AE-32C interactive investigation contract.

These tests use fake providers and evidence tools; they do not contact providers,
execute target-repository code, or apply patches.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32c import (
    InvestigationLimits,
    RepositoryInvestigator,
    render_markdown_report,
    write_report_artifacts,
)


SOURCE = "src/pkg/a.py"
SOURCE_BYTES = b"def run():\n    return 'observed'\n"
SOURCE_HASH = hashlib.sha256(SOURCE_BYTES).hexdigest()


class FakeEvidenceTools:
    def __init__(self, *, change_provenance_on_call=None, extra_result=None):
        self.calls = []
        self.change_provenance_on_call = change_provenance_on_call
        self.extra_result = extra_result or {}
        self.provenance = {
            "source_revision": None,
            "source_revision_status": "not_provided",
            "runner_revision": None,
            "runner_revision_status": "not_provided",
            "source_manifest_sha256": "a" * 64,
            "graph_fingerprint": "b" * 64,
            "graph_projection_version": "test-projection/v1",
            "source_snapshot_status": "complete",
            "evidence_index_status": "complete",
        }
        self.file_hashes = {SOURCE: SOURCE_HASH}

    def invoke(self, tool, arguments):
        self.calls.append((tool, dict(arguments)))
        provenance = dict(self.provenance)
        if self.change_provenance_on_call and len(self.calls) >= self.change_provenance_on_call:
            provenance["graph_fingerprint"] = "c" * 64
        if tool == "repository_summary":
            result = {"audit_status": "complete", "evidence_index_status": "complete", "indexed_file_count": 1, "graph_node_count": 2, "graph_edge_count": 1}
        elif tool == "search_repository":
            result = {"query": arguments["query"], "matches": [{"path": SOURCE, "line": 2, "match_kind": "content", "snippet": "return 'observed'", "source_sha256": SOURCE_HASH}], "truncated": False}
        elif tool == "graph_path":
            result = {"source": arguments["source"], "target": arguments["target"], "observations": [{"path": SOURCE, "line": 1, "source_sha256": SOURCE_HASH, "relation_type": "IMPORTS"}], "truncated": False}
        else:
            result = {"query": str(arguments), "matches": [], "truncated": False}
        if tool != "repository_summary":
            result.update(self.extra_result)
        return {"schema_version": "fake/v1", "tool": tool, "status": "ok", "provenance": provenance, "result": result}


class FakeProvider:
    provider_name = "fake-provider"
    model = "fake-model"

    def __init__(self, responses, on_chat=None):
        self.responses = list(responses)
        self.on_chat = on_chat
        self.messages = []
        self.calls = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reported_cost_usd": 0.0}

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.messages.append([dict(message) for message in messages])
        self.calls += 1
        if self.on_chat is not None:
            self.on_chat()
        self.usage["prompt_tokens"] += 20
        self.usage["completion_tokens"] += 10
        self.usage["total_tokens"] += 30
        if not self.responses:
            return None, "fake provider response queue exhausted"
        item = self.responses.pop(0)
        if isinstance(item, tuple):
            return item
        return item, None

    def get_stats(self):
        return {"provider": self.provider_name, "model": self.model, "usage": dict(self.usage)}


def action_tool(tool, arguments, reason="need additional evidence"):
    return json.dumps({"action": "tool_call", "tool": tool, "arguments": arguments, "reason": reason})


def final_action(*, evidence_id="E0002", source_reference=True, summary="The interface mismatch is supported by retrieved source evidence.", claim_statement="The source search returned a line from the indexed module."):
    source_refs = []
    if source_reference:
        source_refs = [{"evidence_id": evidence_id, "path": SOURCE, "line": 2, "source_sha256": SOURCE_HASH}]
    return json.dumps({
        "action": "final",
        "diagnosis": {
            "summary": summary,
            "root_cause": {
                "statement": "The inspected evidence indicates a likely interface mismatch; the causal interpretation is not independently proven.",
                "confidence": "medium",
                "evidence_refs": [evidence_id],
                "source_references": source_refs,
            },
            "claims": [{
                "statement": claim_statement,
                "kind": "observation",
                "confidence": "high",
                "evidence_refs": [evidence_id],
                "source_references": source_refs,
            }],
            "proposed_corrective_action": "Review the provider interface and its callers before proposing a patch.",
            "limitations": ["Static evidence does not prove runtime execution."],
            "next_steps": ["Inspect the caller, adapter, related tests, and workflow."],
        },
    })


def make_investigator(responses, *, evidence=None, limits=None, cost_estimator=None):
    provider = FakeProvider(responses)
    tools = evidence or FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=tools,
        limits=limits or InvestigationLimits(),
        cost_estimator=cost_estimator,
        id_factory=lambda: "test-investigation-0001",
    )
    return investigator, provider, tools


def test_multiple_rounds_consume_actual_tool_results_and_resolve_citations():
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        action_tool("graph_path", {"source": "module:main", "target": "module:providers.factory", "max_depth": 3}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    report = investigator.run("Investigate the provider total_calls interface failure")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["diagnosis_assurance"] == "references_resolved_not_independently_proven"
    assert report["stop_reason"] == "diagnosis_submitted"
    assert [item["tool"] for item in report["tool_calls"]] == ["repository_summary", "search_repository", "graph_path"]
    assert report["diagnosis"]["root_cause"]["source_references"][0]["line"] == 2
    assert len(provider.messages) == 3
    assert len(tools.calls) == 3
    assert "untrusted evidence" in provider.messages[0][0]["content"]
    assert "E0002" in provider.messages[1][-1]["content"]
    assert "E0003" in provider.messages[2][-1]["content"]


def test_verified_snapshot_can_produce_completed_status(tmp_path: Path):
    repository = tmp_path / "repo"
    source_path = repository / SOURCE
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(SOURCE_BYTES)
    tools = FakeEvidenceTools()
    tools.root = repository
    tools.manifest_rows = {SOURCE: {"size": len(SOURCE_BYTES), "sha256": SOURCE_HASH}}
    tools.manifest_sha256 = "a" * 64
    tools.graph_fingerprint = "b" * 64
    investigator, _, _ = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], evidence=tools)
    report = investigator.run("Investigate a source-level failure")
    assert report["snapshot_check_status"] == "verified"
    assert report["status"] == "completed"


def test_unknown_tool_request_is_rejected_without_dispatch():
    investigator, provider, tools = make_investigator([
        action_tool("run_shell", {"command": "echo unsafe"}),
    ])
    report = investigator.run("Investigate a failed workflow")
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "invalid_tool_request"
    assert len(provider.messages) == 1
    assert [call[0] for call in tools.calls] == ["repository_summary"]


def test_unknown_tool_arguments_are_rejected_before_dispatch():
    investigator, _, tools = make_investigator([
        action_tool("search_repository", {"query": "observed", "unexpected": "extra"}),
    ])
    report = investigator.run("Investigate a failed workflow")
    assert report["stop_reason"] == "invalid_tool_request"
    assert [call[0] for call in tools.calls] == ["repository_summary"]


def test_duplicate_json_keys_are_rejected():
    investigator, _, tools = make_investigator(['{"action":"tool_call","action":"final"}'])
    report = investigator.run("Investigate a failed workflow")
    assert report["stop_reason"] == "invalid_model_json"
    assert len(tools.calls) == 1


def test_sensitive_structured_fields_are_redacted_before_model_context():
    tools = FakeEvidenceTools(extra_result={"api_key": "arbitrary-secret-value-not-token-shaped"})
    investigator, provider, _ = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], evidence=tools)
    report = investigator.run("Investigate a provider failure")
    serialized_context = json.dumps(provider.messages)
    assert report["status"] == "completed_with_incomplete_evidence"
    assert "arbitrary-secret-value-not-token-shaped" not in serialized_context
    assert "arbitrary-secret-value-not-token-shaped" not in json.dumps(report)


def test_provider_failure_is_reported_without_raw_provider_payload():
    investigator, _, _ = make_investigator([(None, "HTTP 400 API_KEY=sk-ABCDEFGHIJKLMNOPQRSTUVWX")])
    report = investigator.run("Investigate a failed workflow")
    serialized = json.dumps(report)
    assert report["stop_reason"] == "provider_failure"
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX" not in serialized
    assert "redacted" in serialized


def test_oversized_model_response_stops_before_json_parsing():
    investigator, _, _ = make_investigator([" " * 2_000], limits=InvestigationLimits(max_response_chars=1_000))
    report = investigator.run("Investigate a failed workflow")
    assert report["stop_reason"] == "provider_response_too_large"
    assert report["status"] == "incomplete"


def test_invalid_citation_is_rejected_and_one_repair_turn_can_succeed():
    bad = final_action(evidence_id="E9999", source_reference=False)
    good = final_action(evidence_id="E0002", source_reference=True, summary="An evidence-referenced assessment with limitations.")
    investigator, provider, _ = make_investigator([
        bad,
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        good,
    ])
    report = investigator.run("Investigate a failed workflow")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert any(event.get("event") == "final_diagnosis_rejected" for event in report["errors"])
    assert len(provider.messages) == 3
    assert report["diagnosis_assurance"] == "references_resolved_not_independently_proven"


def test_unobserved_source_line_is_rejected():
    invalid = json.loads(final_action(evidence_id="E0002", source_reference=True))
    invalid["diagnosis"]["root_cause"]["source_references"][0]["line"] = 999
    invalid["diagnosis"]["claims"][0]["source_references"][0]["line"] = 999
    investigator, _, _ = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        json.dumps(invalid),
    ], limits=InvestigationLimits(max_invalid_final_attempts=0))
    report = investigator.run("Investigate a failed workflow")
    assert report["status"] == "inconclusive"
    assert report["stop_reason"] == "invalid_diagnosis_references_or_schema"


def test_evidence_provenance_mismatch_stops_investigation():
    tools = FakeEvidenceTools(change_provenance_on_call=2)
    investigator, _, _ = make_investigator([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
    ], evidence=tools)
    report = investigator.run("Investigate a provider failure")
    assert report["stop_reason"] == "evidence_provenance_mismatch"
    assert report["status"] == "incomplete"


def test_cost_budget_requires_a_conservative_estimator_before_any_tool_or_provider_call():
    investigator, provider, tools = make_investigator(
        [final_action(evidence_id="E0001", source_reference=False)],
        limits=InvestigationLimits(max_cost_usd=0.01),
    )
    report = investigator.run("Investigate a provider failure")
    assert report["status"] == "invalid_configuration"
    assert report["stop_reason"] == "cost_budget_requires_conservative_estimator"
    assert provider.calls == 0
    assert tools.calls == []


def test_estimated_cost_budget_stops_before_an_over_budget_request():
    investigator, provider, _ = make_investigator(
        [final_action(evidence_id="E0001", source_reference=False)],
        limits=InvestigationLimits(max_cost_usd=0.0001),
        cost_estimator=lambda provider_name, model_name, prompt_chars, max_tokens: 0.001,
    )
    report = investigator.run("Investigate a provider failure")
    assert report["stop_reason"] == "estimated_cost_budget_exhausted"
    assert provider.calls == 0


def test_tool_call_budget_includes_initial_repository_summary():
    investigator, _, _ = make_investigator(
        [action_tool("search_repository", {"query": "x"})],
        limits=InvestigationLimits(max_tool_calls=1),
    )
    report = investigator.run("Investigate a provider failure")
    assert report["stop_reason"] == "tool_call_budget_exhausted"


def test_snapshot_change_during_provider_call_invalidates_the_investigation(tmp_path: Path):
    repository = tmp_path / "repo"
    source_path = repository / SOURCE
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(SOURCE_BYTES)
    tools = FakeEvidenceTools()
    tools.root = repository
    tools.manifest_rows = {SOURCE: {"size": len(SOURCE_BYTES), "sha256": SOURCE_HASH}}
    provider = FakeProvider(
        [final_action(evidence_id="E0001", source_reference=False)],
        on_chat=lambda: source_path.write_text("def changed():\n    return False\n", encoding="utf-8"),
    )
    investigator = RepositoryInvestigator(
        repository,
        provider,
        evidence_tools=tools,
        limits=InvestigationLimits(),
        id_factory=lambda: "test-snapshot-change",
    )
    report = investigator.run("Investigate a source-level failure")
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "snapshot_changed"
    assert report["diagnosis"] is None


def test_markdown_report_does_not_claim_diagnosis_is_independently_proven():
    investigator, _, _ = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    report = investigator.run("Investigate a provider failure")
    markdown = render_markdown_report(report)
    assert "references_resolved_not_independently_proven" in markdown
    assert "Tool-call trace" in markdown


def test_report_writer_refuses_to_publish_inside_inspected_repository(tmp_path: Path):
    repository = tmp_path / "repo"
    output = repository / "reports"
    repository.mkdir()
    output.mkdir()
    with pytest.raises(ValueError, match="outside_repository"):
        write_report_artifacts({"investigation_id": "test", "status": "incomplete"}, output, repository)


def test_report_writer_creates_json_and_markdown_outside_repository(tmp_path: Path):
    repository = tmp_path / "repo"
    output = tmp_path / "reports"
    repository.mkdir()
    output.mkdir()
    report = {"investigation_id": "test-run-01", "status": "incomplete", "stop_reason": "test", "provider": {}, "provenance": {}, "problem_statement": "test", "tool_calls": [], "limitations": []}
    result = write_report_artifacts(report, output, repository)
    assert result["publication"] == "exclusive_atomic_link"
    assert len(result["artifacts"]) == 2
    assert all(Path(item["path"]).is_file() for item in result["artifacts"])
    assert all(len(item["sha256"]) == 64 for item in result["artifacts"])

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
        self.max_retries = 3
        self.max_retries_seen = []
        self.http_attempts = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reported_cost_usd": 0.0}

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.messages.append([dict(message) for message in messages])
        self.max_retries_seen.append(self.max_retries)
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
        return {
            "provider": self.provider_name,
            "model": self.model,
            "http_attempts": self.http_attempts,
            "usage": dict(self.usage),
        }


class StructuredCloudflareFakeProvider(FakeProvider):
    provider_name = "cloudflare"

    def __init__(self, responses, on_chat=None):
        super().__init__(responses, on_chat=on_chat)
        self.structured_calls = 0

    def get_capabilities(self):
        return {
            "json_object_mode": True,
            "json_schema_mode": False,
            "native_tool_calls": False,
            "finish_reason_reporting": False,
        }

    def chat_structured(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.structured_calls += 1
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)


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
    assert report["stop_reason"] == "diagnosis_submitted_with_coverage_or_snapshot_limitations"
    assert [item["tool"] for item in report["tool_calls"]] == ["repository_summary", "search_repository", "graph_path"]
    assert report["diagnosis"]["root_cause"]["source_references"][0]["line"] == 2
    assert len(provider.messages) == 3
    assert len(tools.calls) == 3
    assert "untrusted evidence" in provider.messages[0][0]["content"]
    assert "E0002" in provider.messages[1][-1]["content"]
    assert "E0003" in provider.messages[2][-1]["content"]



def test_finalization_rounds_reject_extra_tools_and_reach_final_diagnosis():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=2,
        max_tool_calls=8,
        max_tokens_per_call=1_000,
        max_total_tokens=32_000,
        max_total_prompt_chars=500_000,
        max_elapsed_seconds=30,
    )
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        action_tool("graph_path", {"source": "module:main", "target": "module:providers.factory", "max_depth": 3}),
        action_tool("search_repository", {"query": "another detail", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=limits)

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["status"] == "completed_with_incomplete_evidence", (
        f"stop_reason={report.get('stop_reason')!r}; budget={report.get('budget')!r}; "
        f"errors={report.get('errors')!r}"
    )
    assert report["stop_reason"] == "diagnosis_submitted_with_coverage_or_snapshot_limitations"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository", "graph_path"]
    assert report["budget"]["finalization_rounds_reserved"] == 2
    assert report["budget"]["finalization_start_round"] == 3
    assert report["budget"]["finalization_rounds_used"] == 2
    assert report["budget"]["finalization_tool_requests_rejected"] == 1
    assert any(event.get("event") == "finalization_tool_request_rejected" for event in report["errors"])
    assert "finalization_mode" in provider.messages[2][-1]["content"]
    assert any("validation_feedback" in message["content"] for message in provider.messages[3])


def test_repeated_tool_requests_during_finalization_stop_without_dispatch():
    limits = InvestigationLimits(
        max_rounds=3,
        finalization_rounds_reserved=2,
        max_tool_calls=8,
        max_tokens_per_call=1_000,
        max_total_tokens=12_000,
        max_total_prompt_chars=500_000,
        max_elapsed_seconds=30,
    )
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        action_tool("graph_path", {"source": "module:main", "target": "module:providers.factory", "max_depth": 3}),
        action_tool("search_repository", {"query": "more", "mode": "content", "max_results": 5}),
    ], limits=limits)

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["status"] == "inconclusive"
    assert report["stop_reason"] == "finalization_budget_exhausted"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    assert report["budget"]["finalization_rounds_used"] == 2
    assert report["budget"]["finalization_tool_requests_rejected"] == 2
    assert len(provider.messages) == 3

def test_invalid_final_action_shape_gets_one_bounded_correction_turn():
    invalid = json.loads(final_action(evidence_id="E0002", source_reference=True))
    invalid["unexpected"] = "do-not-echo-this-value"
    invalid_response = json.dumps(invalid)
    limits = InvestigationLimits(
        max_rounds=3,
        finalization_rounds_reserved=2,
        max_invalid_final_attempts=1,
        max_tool_calls=5,
        max_tokens_per_call=1_000,
        max_total_tokens=32_000,
        max_total_prompt_chars=500_000,
        max_elapsed_seconds=30,
    )
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        invalid_response,
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=limits)

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["diagnosis"] is not None
    assert report["budget"]["invalid_final_attempts_used"] == 1
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    serialized = json.dumps({"messages": provider.messages, "report": report})
    assert "do-not-echo-this-value" not in serialized
    assert any(
        event.get("event") == "final_action_rejected"
        and event.get("reason_code") == "final_action_shape_invalid"
        and event.get("received_keys") == ["action", "diagnosis", "unexpected"]
        for event in report["errors"]
    )
    assert "expected_top_level_keys" in json.dumps(provider.messages)


def test_repeated_invalid_final_action_shape_stops_after_one_recovery():
    invalid = json.loads(final_action(evidence_id="E0002", source_reference=True))
    invalid["unexpected"] = "do-not-echo-this-value"
    invalid_response = json.dumps(invalid)
    limits = InvestigationLimits(
        max_rounds=3,
        finalization_rounds_reserved=2,
        max_invalid_final_attempts=1,
        max_tool_calls=5,
        max_tokens_per_call=1_000,
        max_total_tokens=32_000,
        max_total_prompt_chars=500_000,
        max_elapsed_seconds=30,
    )
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        invalid_response,
        invalid_response,
    ], limits=limits)

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "invalid_final_action"
    assert report["budget"]["invalid_final_attempts_used"] == 2
    assert len(tools.calls) == 2
    assert any(event.get("event") == "final_action_recovery_exhausted" for event in report["errors"])
    assert "do-not-echo-this-value" not in json.dumps({"messages": provider.messages, "report": report})


def test_cloudflare_investigator_uses_structured_provider_method():
    provider = StructuredCloudflareFakeProvider([
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    tools = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        provider_name="cloudflare",
        evidence_tools=tools,
        limits=InvestigationLimits(max_total_tokens=32_000, max_total_prompt_chars=500_000),
        id_factory=lambda: "test-cloudflare-structured-json",
    )

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert provider.structured_calls == 2
    assert sum(event.get("event") == "provider_structured_json_mode_requested" for event in report["errors"]) == 2


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


def test_unknown_tool_request_is_rejected_without_dispatch_when_recovery_disabled():
    investigator, provider, tools = make_investigator([
        action_tool("run_shell", {"command": "echo unsafe"}),
    ], limits=InvestigationLimits(max_invalid_tool_retries=0))
    report = investigator.run("Investigate a failed workflow")
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "invalid_tool_request"
    assert len(provider.messages) == 1
    assert [call[0] for call in tools.calls] == ["repository_summary"]
    assert any(event.get("event") == "tool_action_recovery_exhausted" for event in report["errors"])


def test_invalid_tool_action_envelope_reports_top_level_keys_and_recovers_safely():
    invalid = json.loads(action_tool(
        "search_repository",
        {"query": "observed", "mode": "content", "max_results": 5},
    ))
    invalid["unexpected_envelope_key"] = "do-not-echo-this-value"
    investigator, provider, tools = make_investigator([
        json.dumps(invalid),
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=InvestigationLimits(max_invalid_tool_retries=1))

    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    assert report["budget"]["invalid_tool_retries_used"] == 1
    rejection = next(
        event for event in report["errors"]
        if event.get("event") == "model_action_rejected"
        and event.get("reason_code") == "tool_action_shape_invalid"
    )
    assert rejection["received_top_level_keys"] == [
        "action", "arguments", "reason", "tool", "unexpected_envelope_key"
    ]
    assert rejection["missing_top_level_keys"] == []
    assert rejection["unexpected_top_level_keys"] == ["unexpected_envelope_key"]
    recovery = next(
        event for event in report["errors"]
        if event.get("event") == "tool_action_recovery_offered"
        and event.get("reason_code") == "tool_action_shape_invalid"
    )
    assert recovery["top_level_shape_guidance"] is True
    feedback = json.loads(provider.messages[1][-1]["content"])["validation_feedback"]
    assert feedback["expected_top_level_keys"] == ["action", "arguments", "reason", "tool"]
    assert feedback["unexpected_top_level_keys"] == ["unexpected_envelope_key"]
    assert "Put all tool parameters inside the arguments object" in feedback["message"]
    serialized = json.dumps({"messages": provider.messages, "report": report})
    assert "do-not-echo-this-value" not in serialized


def test_unknown_tool_arguments_receive_feedback_and_recover_once():
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "observed", "unexpected": "extra"}),
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    report = investigator.run("Investigate a failed workflow")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    assert report["budget"]["invalid_tool_retries_used"] == 1
    feedback_envelope = json.loads(provider.messages[1][-1]["content"])
    feedback = feedback_envelope["validation_feedback"]
    assert feedback["status"] == "rejected_before_dispatch"
    assert feedback["unknown_fields"] == ["unexpected"]
    assert "No evidence tool was executed" in feedback["message"]
    assert any(event.get("event") == "tool_action_recovery_offered" for event in report["errors"])


def test_invalid_enum_receives_allowed_values_and_corrected_action_succeeds():
    investigator, provider, tools = make_investigator([
        action_tool("search_symbols", {"query": "total_calls", "kind": "method", "max_results": 5}),
        action_tool("search_symbols", {"query": "total_calls", "kind": "function", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=False),
    ])
    report = investigator.run("Investigate a provider interface failure")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["stop_reason"] == "diagnosis_submitted_with_coverage_or_snapshot_limitations"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_symbols"]
    feedback_envelope = json.loads(provider.messages[1][-1]["content"])
    feedback = feedback_envelope["validation_feedback"]
    assert feedback["field_guidance"] == [{
        "field": "kind",
        "allowed_values": ["any", "class", "function", "async_function"],
    }]
    assert '"method"' not in json.dumps(feedback)
    assert report["budget"]["invalid_tool_retries_used"] == 1


def test_repeated_invalid_tool_schema_stops_after_one_correction_opportunity():
    investigator, provider, tools = make_investigator([
        action_tool("search_symbols", {"query": "total_calls", "kind": "method", "max_results": 5}),
        action_tool("search_symbols", {"query": "total_calls", "kind": "property", "max_results": 5}),
    ], limits=InvestigationLimits(max_invalid_tool_retries=1))
    report = investigator.run("Investigate a provider interface failure")
    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "invalid_tool_request"
    assert report["budget"]["invalid_tool_retries_used"] == 1
    assert report["budget"]["max_invalid_tool_retries"] == 1
    assert [call[0] for call in tools.calls] == ["repository_summary"]
    assert len(provider.messages) == 2
    assert any(event.get("event") == "tool_action_recovery_exhausted" for event in report["errors"])


def test_mismatched_tool_arguments_feedback_suggests_the_matching_registered_tool():
    investigator, provider, tools = make_investigator([
        action_tool("graph_path", {"query": "total_calls", "mode": "content", "max_results": 5}),
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    report = investigator.run("Find source references for the total_calls attribute access.")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    feedback = json.loads(provider.messages[1][-1]["content"])["validation_feedback"]
    assert feedback["requested_tool"] == "graph_path"
    assert "source" in feedback["accepted_argument_names"]
    assert "target" in feedback["accepted_argument_names"]
    assert feedback["unknown_fields"] == ["max_results", "mode", "query"]
    assert feedback["possible_tool_matches"][0]["name"] == "search_repository"
    assert feedback["possible_tool_matches"][0]["matching_fields"] == ["max_results", "mode", "query"]
    assert report["budget"]["invalid_tool_retries_used"] == 1


def test_multiple_invalid_tool_actions_can_recover_within_global_bound():
    investigator, provider, tools = make_investigator([
        action_tool("graph_path", {"query": "total_calls", "mode": "content", "max_results": 5}),
        action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
        action_tool("read_source_file", {"query": "total_calls"}),
        action_tool("graph_path", {"source": "module:main", "target": "module:providers.factory", "max_depth": 3}),
        final_action(evidence_id="E0002", source_reference=True),
    ])
    report = investigator.run("Investigate the provider interface failure.")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository", "graph_path"]
    assert report["budget"]["invalid_tool_retries_used"] == 2
    assert report["budget"]["max_invalid_tool_retries"] == 3
    assert sum(event.get("event") == "tool_action_recovery_offered" for event in report["errors"]) == 2
    assert len(provider.messages) == 5


def test_failed_source_read_gives_exact_path_recovery_guidance():
    class MissingPathEvidenceTools(FakeEvidenceTools):
        def invoke(self, tool, arguments):
            if tool == "read_source_file":
                self.calls.append((tool, dict(arguments)))
                return {
                    "schema_version": "fake/v1",
                    "tool": tool,
                    "status": "error",
                    "error": {
                        "code": "invalid_path",
                        "message": "Absolute paths are not accepted",
                    },
                    "provenance": dict(self.provenance),
                }
            return super().invoke(tool, arguments)

    tools = MissingPathEvidenceTools()
    tools.file_hashes["providers/adapter.py"] = hashlib.sha256(
        b"class ProviderAdapter:\n    pass\n"
    ).hexdigest()
    investigator, provider, _ = make_investigator([
        action_tool("read_source_file", {"path": "/path/to/provider.py", "start_line": 1, "end_line": 10}),
        action_tool("search_repository", {"query": "ProviderAdapter", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0003", source_reference=True),
    ], evidence=tools)
    report = investigator.run("Inspect the provider adapter for the interface mismatch.")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "read_source_file", "search_repository"]
    feedback = json.loads(provider.messages[1][-1]["content"])["validation_feedback"]
    assert feedback["schema_version"] == "ae32c/source-path-guidance/v1"
    assert feedback["reason_code"] == "invalid_path"
    assert "exact repository-relative path" in feedback["message"]
    assert "providers/adapter.py" in feedback["possible_indexed_paths"]
    assert report["budget"]["source_path_guidance_used"] == 1


def test_duplicate_json_keys_are_rejected_when_json_recovery_is_disabled():
    investigator, provider, tools = make_investigator(
        ['{"action":"tool_call","action":"final"}'],
        limits=InvestigationLimits(max_invalid_json_retries=0),
    )
    report = investigator.run("Investigate a failed workflow")
    assert report["stop_reason"] == "invalid_model_json"
    assert len(provider.messages) == 1
    assert len(tools.calls) == 1
    assert report["budget"]["invalid_json_retries_used"] == 0
    assert any(event.get("event") == "invalid_json_recovery_exhausted" for event in report["errors"])


def test_finalization_json_recovery_uses_reserved_rounds_and_can_finish():
    malformed_one = "not json response one"
    malformed_two = "not json response two"
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_invalid_json_retries=2,
        max_finalization_invalid_json_retries=2,
        max_tool_calls=5,
        max_tokens_per_call=1_000,
        max_total_tokens=32_000,
        max_total_prompt_chars=500_000,
        max_elapsed_seconds=30,
    )
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        malformed_one,
        malformed_two,
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=limits)

    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["stop_reason"] == "diagnosis_submitted_with_coverage_or_snapshot_limitations"
    assert report["budget"]["model_rounds_used"] == 4
    assert report["budget"]["finalization_rounds_reserved"] == 3
    assert report["budget"]["finalization_rounds_used"] == 3
    assert report["budget"]["invalid_json_retries_used"] == 2
    assert report["budget"]["evidence_gathering_invalid_json_retries_used"] == 0
    assert report["budget"]["finalization_invalid_json_retries_used"] == 2
    assert report["budget"]["max_invalid_json_retries_total"] == 4
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    serialized = json.dumps({"messages": provider.messages, "report": report})
    assert malformed_one not in serialized
    assert malformed_two not in serialized
    unique_feedback = {}
    for turn in provider.messages:
        for message in turn:
            content = message.get("content", "")
            if message.get("role") != "user" or "validation_feedback" not in content:
                continue
            try:
                envelope = json.loads(content)
            except json.JSONDecodeError:
                continue
            feedback = envelope.get("validation_feedback")
            if isinstance(feedback, dict) and feedback.get("schema_version") == "ae32c/json-validation-feedback/v1":
                unique_feedback[content] = feedback
    finalization_feedback = [
        item for item in unique_feedback.values()
        if item.get("phase") == "finalization"
    ]
    assert len(finalization_feedback) == 2
    assert all(item["required_action"] == "final" for item in finalization_feedback)
    assert all(item["required_top_level_keys"] == ["action", "diagnosis"] for item in finalization_feedback)
    syntax_events = [
        item for item in report["errors"]
        if item.get("event") == "model_action_rejected"
        and item.get("parse_error_code") == "json_syntax_error"
    ]
    assert len(syntax_events) == 2
    assert all(item["parse_error_line"] == 1 and item["parse_error_column"] == 1 for item in syntax_events)


def test_finalization_json_recovery_remains_available_after_evidence_budget_is_used():
    malformed_evidence_one = "malformed evidence response one; must not be retained"
    malformed_evidence_two = "malformed evidence response two; must not be retained"
    malformed_finalization = "malformed finalization response; must not be retained"
    search = action_tool(
        "search_repository",
        {"query": "provider.total_calls", "mode": "content", "max_results": 5},
    )
    investigator, provider, tools = make_investigator([
        search,                         # round 1
        search,                         # round 2
        search,                         # round 3
        search,                         # round 4
        malformed_evidence_one,         # round 5: evidence recovery 1
        search,                         # round 6
        malformed_evidence_two,         # round 7: evidence recovery 2 (evidence budget exhausted)
        malformed_finalization,         # round 8: finalization gets its independent recovery
        final_action(evidence_id="E0002", source_reference=True),  # round 9
    ], limits=InvestigationLimits(
        max_rounds=10,
        finalization_rounds_reserved=3,
        max_invalid_json_retries=2,
        max_finalization_invalid_json_retries=1,
        # This test isolates phase-scoped JSON recovery. The growing fake
        # conversation history must not accidentally hit unrelated prompt or
        # estimated-token budgets before the expected final response.
        max_total_tokens=180_000,
        max_total_prompt_chars=500_000,
    ))

    report = investigator.run("Investigate the provider interface mismatch.")

    assert report["diagnosis"] is not None, (
        f"stop_reason={report.get('stop_reason')!r}; "
        f"budget={report.get('budget')!r}; "
        f"errors={report.get('errors')!r}; "
        f"model_actions={report.get('model_actions')!r}"
    )
    assert report["budget"]["model_rounds_used"] == 9
    assert report["budget"]["invalid_json_retries_used"] == 3
    assert report["budget"]["max_invalid_json_retries"] == 2
    assert report["budget"]["evidence_gathering_invalid_json_retries_used"] == 2
    assert report["budget"]["max_evidence_gathering_invalid_json_retries"] == 2
    assert report["budget"]["finalization_invalid_json_retries_used"] == 1
    assert report["budget"]["max_finalization_invalid_json_retries"] == 1
    assert report["budget"]["max_invalid_json_retries_total"] == 3

    feedback = []
    for turn in provider.messages:
        for message in turn:
            content = message.get("content", "")
            if not isinstance(content, str):
                continue
            try:
                envelope = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(envelope, dict):
                continue
            candidate = envelope.get("validation_feedback")
            if (
                isinstance(candidate, dict)
                and candidate.get("schema_version") == "ae32c/json-validation-feedback/v1"
            ):
                feedback.append(candidate)

    final_feedback = [item for item in feedback if item.get("phase") == "finalization"]
    assert len(final_feedback) == 1
    assert final_feedback[0]["recovery_attempt"] == 1
    assert final_feedback[0]["total_recovery_attempts_used"] == 3
    assert final_feedback[0]["remaining_recovery_attempts"] == 0
    assert final_feedback[0]["required_action"] == "final"

    offered = [
        event for event in report["errors"]
        if event.get("event") == "invalid_json_recovery_offered"
    ]
    assert [(event["round"], event["phase"]) for event in offered] == [
        (5, "evidence_gathering"),
        (7, "evidence_gathering"),
        (8, "finalization"),
    ]
    assert not any(
        event.get("event") == "invalid_json_recovery_exhausted"
        for event in report["errors"]
    )
    serialized = json.dumps({"messages": provider.messages, "report": report})
    assert malformed_evidence_one not in serialized
    assert malformed_evidence_two not in serialized
    assert malformed_finalization not in serialized
    # The finalization-only recovery must not dispatch another tool.
    assert [name for name, _ in tools.calls].count("search_repository") == 5


def test_finalization_uses_reserved_rounds_across_mixed_response_failures():
    malformed = "malformed finalization JSON; must not be echoed"
    invalid_envelope = json.dumps({
        "action": "final",
        "diagnosis": {},
        "limitations": ["extra top-level key"],
    })
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "adapter", "mode": "content", "max_results": 5}),
        malformed,
        invalid_envelope,
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_invalid_json_retries=2,
        max_finalization_invalid_json_retries=1,
        max_invalid_final_attempts=1,
    ))

    report = investigator.run("Investigate the provider adapter interface.")

    assert report["diagnosis"] is not None, (
        "mixed finalization recovery failed: "
        f"stop_reason={report.get('stop_reason')!r}; "
        f"budget={report.get('budget')!r}; "
        f"errors={report.get('errors')!r}; "
        f"model_actions={report.get('model_actions')!r}"
    )
    assert report["budget"]["finalization_rounds_used"] == 3
    assert report["budget"]["finalization_rounds_reserved"] == 3
    assert report["budget"]["finalization_rejections_used"] == 2
    assert report["budget"]["finalization_invalid_json_retries_used"] == 1
    assert report["budget"]["invalid_final_attempts_used"] == 1
    assert report["stop_reason"] in {
        "diagnosis_submitted",
        "diagnosis_submitted_with_coverage_or_snapshot_limitations",
    }
    if report["stop_reason"] == "diagnosis_submitted":
        assert report["status"] == "completed"
    else:
        # This small fixture does not establish complete evidence coverage or a
        # fully verified snapshot. Preserve that limitation rather than treating
        # it as a production failure or weakening the engine's acceptance gate.
        assert report["status"] == "completed_with_incomplete_evidence"
    assert malformed not in json.dumps({"messages": provider.messages, "report": report})
    assert len(tools.calls) == 2


def test_malformed_json_gets_one_bounded_recovery_and_can_continue():
    malformed = "I will search the repository now. ```json {not valid}"
    investigator, provider, tools = make_investigator([
        malformed,
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=InvestigationLimits(max_invalid_json_retries=1))
    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["stop_reason"] == "diagnosis_submitted_with_coverage_or_snapshot_limitations"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    assert report["budget"]["invalid_json_retries_used"] == 1
    assert report["budget"]["max_invalid_json_retries"] == 1
    assert len(provider.messages) == 3
    recovery_context = json.dumps(provider.messages[1])
    assert "ae32c/json-validation-feedback/v1" in recovery_context
    assert "exactly one valid strict JSON object" in recovery_context
    assert malformed not in json.dumps(provider.messages)
    assert malformed not in json.dumps(report)
    syntax_event = next(
        event for event in report["errors"]
        if event.get("event") == "model_action_rejected"
        and event.get("parse_error_code") == "json_syntax_error"
    )
    assert syntax_event["parse_error_line"] == 1
    assert syntax_event["parse_error_column"] == 1
    assert any(event.get("event") == "invalid_json_recovery_offered" for event in report["errors"])


def test_repeated_malformed_json_stops_after_bounded_retries():
    investigator, provider, tools = make_investigator(
        ["not json one", "not json two", final_action(evidence_id="E0001", source_reference=False)],
        limits=InvestigationLimits(max_invalid_json_retries=1),
    )
    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "invalid_model_json"
    assert len(provider.messages) == 2
    assert len(tools.calls) == 1
    assert report["budget"]["invalid_json_retries_used"] == 1
    assert any(event.get("event") == "invalid_json_recovery_exhausted" for event in report["errors"])


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


def test_invalid_source_references_receive_exact_ledger_candidates_and_recover_twice():
    invalid_line = json.loads(final_action(evidence_id="E0002", source_reference=True))
    invalid_line["diagnosis"]["root_cause"]["source_references"][0]["line"] = 0
    invalid_line["diagnosis"]["claims"][0]["source_references"][0]["line"] = 0

    invalid_shape = json.loads(final_action(evidence_id="E0002", source_reference=True))
    invalid_shape["diagnosis"]["root_cause"]["source_references"][0]["extra"] = "not permitted"
    invalid_shape["diagnosis"]["claims"][0]["source_references"][0]["extra"] = "not permitted"

    investigator, provider, _ = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        json.dumps(invalid_line),
        json.dumps(invalid_shape),
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=InvestigationLimits(max_invalid_final_attempts=2))

    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert report["diagnosis"] is not None
    rejected = [
        event for event in report["errors"]
        if event.get("event") == "final_diagnosis_rejected"
    ]
    assert len(rejected) == 2
    assert "source_reference_line_invalid" in rejected[0]["reason_codes"]
    assert "source_reference_shape_invalid" in rejected[1]["reason_codes"]

    feedback_envelopes = []
    for turn in provider.messages[2:]:
        if not turn:
            continue
        try:
            envelope = json.loads(turn[-1].get("content", ""))
        except json.JSONDecodeError:
            continue
        feedback = envelope.get("validation_feedback") if isinstance(envelope, dict) else None
        if isinstance(feedback, dict) and feedback.get("schema_version") == "ae32c/diagnosis-validation-feedback/v1":
            feedback_envelopes.append(feedback)

    assert len(feedback_envelopes) == 2
    candidate = {
        "evidence_id": "E0002",
        "path": SOURCE,
        "line": 2,
        "source_sha256": SOURCE_HASH,
    }
    assert candidate in feedback_envelopes[0]["source_reference_candidates"]
    assert feedback_envelopes[0]["required_source_reference_keys"] == [
        "evidence_id", "path", "line", "source_sha256"
    ]
    assert "line must be a positive JSON integer" in " ".join(feedback_envelopes[0]["rules"])
    assert "Do not invent citations" in feedback_envelopes[1]["message"]


def test_unsupported_action_gets_safe_bounded_recovery_and_can_continue():
    unsupported = json.dumps({
        "action": "search_repository",
        "query": "sensitive-untrusted-query-must-not-be-echoed",
        "reason": "attempted direct tool name",
    })
    investigator, provider, tools = make_investigator([
        unsupported,
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ])

    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    assert report["budget"]["unsupported_action_retries_used"] == 1
    rejection = next(
        event for event in report["errors"]
        if event.get("event") == "model_action_rejected"
        and event.get("reason") == "unsupported_action"
    )
    assert rejection["received_action_name"] == "search_repository"
    assert rejection["received_top_level_keys"] == ["action", "query", "reason"]
    offered = next(
        event for event in report["errors"]
        if event.get("event") == "unsupported_action_recovery_offered"
    )
    assert offered["tool_dispatch_count"] == 0
    feedback = json.loads(provider.messages[1][-1]["content"])["validation_feedback"]
    assert feedback["supported_action_values"] == ["tool_call", "final"]
    assert feedback["required_envelopes"]["tool_call"]["top_level_keys"] == [
        "action", "tool", "arguments", "reason"
    ]
    serialized = json.dumps({"messages": provider.messages, "report": report})
    assert "sensitive-untrusted-query-must-not-be-echoed" not in serialized


def test_unsupported_action_during_finalization_only_allows_final_recovery():
    unsupported = json.dumps({
        "action": "search_repository",
        "query": "must-not-dispatch-during-finalization",
        "reason": "unsupported direct action",
    })
    investigator, provider, tools = make_investigator([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        unsupported,
        final_action(evidence_id="E0002", source_reference=True),
    ], limits=InvestigationLimits(max_rounds=4, finalization_rounds_reserved=3))

    report = investigator.run("Investigate a failed workflow")

    assert report["diagnosis"] is not None
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    # The provider records a complete message history per request. The feedback
    # is not guaranteed to be the final message at a fixed request index, so
    # locate it by its stable schema identifier rather than message position.
    feedback = None
    for turn in provider.messages:
        for message in turn:
            content = message.get("content", "")
            if not isinstance(content, str):
                continue
            try:
                envelope = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(envelope, dict):
                continue
            candidate = envelope.get("validation_feedback")
            if (
                isinstance(candidate, dict)
                and candidate.get("schema_version") == "ae32c/unsupported-action-feedback/v1"
            ):
                feedback = candidate
                break
        if feedback is not None:
            break

    assert feedback is not None, "finalization unsupported-action feedback was not recorded"
    assert feedback["phase"] == "finalization"
    assert feedback["supported_action_values"] == ["final"]
    assert "Do not request tools" in feedback["message"]
    assert "must-not-dispatch-during-finalization" not in json.dumps(provider.messages)


def test_unsupported_action_recovery_stops_at_configured_bound():
    unsupported = json.dumps({"action": "search_repository", "query": "not-echoed"})
    investigator, provider, tools = make_investigator(
        [unsupported, unsupported, final_action(evidence_id="E0001", source_reference=False)],
        limits=InvestigationLimits(max_invalid_tool_retries=1),
    )

    report = investigator.run("Investigate a failed workflow")

    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "unsupported_model_action"
    assert report["budget"]["unsupported_action_retries_used"] == 1
    assert report["budget"]["model_rounds_used"] == 2
    assert len(tools.calls) == 1
    assert any(event.get("event") == "unsupported_action_recovery_exhausted" for event in report["errors"])


def test_cloudflare_gets_one_investigation_wide_transport_retry_then_single_attempts():
    class RetryAwareCloudflareProvider(StructuredCloudflareFakeProvider):
        def __init__(self, responses, attempts_per_call):
            super().__init__(responses)
            self.attempts_per_call = list(attempts_per_call)

        def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
            self.http_attempts += self.attempts_per_call.pop(0)
            return super().chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)

    provider = RetryAwareCloudflareProvider([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], attempts_per_call=[2, 1])
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=FakeEvidenceTools(),
        limits=InvestigationLimits(),
        id_factory=lambda: "test-investigation-cloudflare-retry",
    )

    report = investigator.run("Investigate a failed workflow")

    assert report["diagnosis"] is not None
    assert provider.max_retries_seen == [2, 1]
    assert provider.max_retries == 3
    assert report["budget"]["max_cloudflare_transport_retries"] == 1
    assert report["budget"]["cloudflare_transport_retries_used"] == 1
    retry_events = [
        event for event in report["errors"]
        if event.get("event") == "cloudflare_transport_retry_budget_consumed"
    ]
    assert retry_events == [{
        "event": "cloudflare_transport_retry_budget_consumed",
        "round": 1,
        "http_attempts": 2,
        "retry_attempts": 1,
        "retry_budget_remaining": 0,
    }]


def test_nararouter_gets_one_global_transport_retry_then_returns_to_single_attempts():
    class RetryAwareNaraProvider(FakeProvider):
        provider_name = "nararouter"

        def __init__(self, responses, attempts_per_call):
            super().__init__(responses)
            self.attempts_per_call = list(attempts_per_call)

        def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
            attempts = self.attempts_per_call.pop(0)
            self.http_attempts += attempts
            return super().chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)

    provider = RetryAwareNaraProvider([
        action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
        final_action(evidence_id="E0002", source_reference=True),
    ], attempts_per_call=[2, 1])
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=FakeEvidenceTools(),
        limits=InvestigationLimits(),
        id_factory=lambda: "test-investigation-nararouter-retry",
    )

    report = investigator.run("Investigate a failed workflow")

    assert report["diagnosis"] is not None
    assert provider.max_retries_seen == [2, 1]
    assert provider.max_retries == 3
    assert report["budget"]["max_nararouter_transport_retries"] == 1
    assert report["budget"]["nararouter_transport_retries_used"] == 1
    retry_events = [
        event for event in report["errors"]
        if event.get("event") == "nararouter_transport_retry_budget_consumed"
    ]
    assert retry_events == [{
        "event": "nararouter_transport_retry_budget_consumed",
        "round": 1,
        "http_attempts": 2,
        "retry_attempts": 1,
        "retry_budget_remaining": 0,
    }]


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


def test_token_budget_rejection_reports_reservation_math_without_prompt_content():
    provider = FakeProvider([])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=evidence,
        limits=InvestigationLimits(
            max_rounds=2,
            max_tool_calls=2,
            max_tokens_per_call=64,
            max_total_tokens=256,
            max_total_prompt_chars=500_000,
            max_elapsed_seconds=30,
        ),
        id_factory=lambda: "ae32c-budget-diagnostic-test",
    )
    report = investigator.run("Inspect the provider interface mismatch.")

    assert report["stop_reason"] == "estimated_token_budget_exhausted"
    check = report["budget"]["last_provider_reservation_check"]
    assert check["decision"] == "rejected"
    assert check["reason"] == "estimated_token_budget_exhausted"
    assert check["prompt_chars_this_call"] > 0
    assert check["requested_reservation_tokens"] > check["max_total_tokens"]
    assert check["reserved_before_tokens"] == 0
    assert "messages" not in check
    assert "prompt" not in check

"""Regression tests for AE-32C Phase E.1 finalization reliability."""
from __future__ import annotations

import json

from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
import hashlib

SOURCE = "src/pkg/a.py"
SOURCE_BYTES = b"def run():\\n    return 'observed'\\n"
SOURCE_HASH = hashlib.sha256(SOURCE_BYTES).hexdigest()


class FakeEvidenceTools:
    def __init__(self):
        self.calls = []
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
        if tool == "repository_summary":
            result = {
                "audit_status": "complete",
                "evidence_index_status": "complete",
                "indexed_file_count": 1,
                "graph_node_count": 2,
                "graph_edge_count": 1,
            }
        elif tool == "search_repository":
            result = {
                "query": arguments["query"],
                "matches": [{
                    "path": SOURCE,
                    "line": 2,
                    "match_kind": "content",
                    "snippet": "return 'observed'",
                    "source_sha256": SOURCE_HASH,
                }],
                "truncated": False,
            }
        elif tool == "graph_path":
            result = {
                "source": arguments["source"],
                "target": arguments["target"],
                "observations": [{
                    "path": SOURCE,
                    "line": 1,
                    "source_sha256": SOURCE_HASH,
                    "relation_type": "IMPORTS",
                }],
                "truncated": False,
            }
        else:
            result = {"query": str(arguments), "matches": [], "truncated": False}
        return {
            "schema_version": "fake/v1",
            "tool": tool,
            "status": "ok",
            "provenance": dict(self.provenance),
            "result": result,
        }


class FakeProvider:
    provider_name = "fake-provider"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []
        self.calls = 0
        self.max_retries = 3
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reported_cost_usd": 0.0}

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.messages.append([dict(message) for message in messages])
        self.calls += 1
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
            "http_attempts": 0,
            "usage": dict(self.usage),
        }


def action_tool(tool, arguments, reason="need additional evidence"):
    return json.dumps({"action": "tool_call", "tool": tool, "arguments": arguments, "reason": reason})


def final_action(*, evidence_id="E0002", source_reference=True):
    source_refs = [{
        "evidence_id": evidence_id,
        "path": SOURCE,
        "line": 2,
        "source_sha256": SOURCE_HASH,
    }] if source_reference else []
    return json.dumps({
        "action": "final",
        "diagnosis": {
            "summary": "The available source evidence suggests an interface mismatch.",
            "root_cause": {
                "statement": "The observed source evidence supports a likely interface mismatch, but does not prove runtime causation.",
                "confidence": "medium",
                "evidence_refs": [evidence_id],
                "source_references": source_refs,
            },
            "claims": [{
                "statement": "The source search returned the observed source line.",
                "kind": "observation",
                "confidence": "high",
                "evidence_refs": [evidence_id],
                "source_references": source_refs,
            }],
            "proposed_corrective_action": "Review the interface and callers.",
            "limitations": ["Static evidence does not prove runtime execution."],
            "next_steps": ["Inspect related source and tests."],
        },
    })


def _investigator(responses, *, limits, evidence=None):
    provider = FakeProvider(responses)
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=evidence or FakeEvidenceTools(),
        limits=limits,
        id_factory=lambda: "phase-e1-regression",
    )
    return investigator, provider


def test_finalization_json_retry_limit_is_enforced_in_finalization():
    malformed = "not-json-and-must-not-be-retained"
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_finalization_invalid_json_retries=1,
        max_finalization_recovery_retries=2,
        max_total_tokens=32_000,
        max_total_prompt_chars=100_000,
    )
    investigator, provider = _investigator(
        [
            action_tool("search_repository", {"query": "total_calls", "mode": "content", "max_results": 5}),
            malformed,
            malformed,
            final_action(evidence_id="E0002", source_reference=True),
        ],
        limits=limits,
    )

    report = investigator.run("Investigate the provider interface mismatch.")

    assert report["diagnosis"] is None
    assert report["stop_reason"] == "invalid_model_json"
    assert report["budget"]["model_rounds_used"] == 3
    assert report["budget"]["finalization_invalid_json_retries_used"] == 1
    assert report["budget"]["finalization_rejections_used"] == 2
    assert any(
        event.get("event") == "invalid_json_recovery_exhausted"
        and event.get("phase") == "finalization"
        and event.get("phase_retry_limit") == 1
        for event in report["errors"]
    )
    assert malformed not in json.dumps({"messages": provider.messages, "report": report})


def test_mixed_finalization_failures_share_one_recovery_budget():
    invalid_envelope = json.loads(final_action(evidence_id="E0002", source_reference=True))
    invalid_envelope["unexpected"] = "must-not-be-echoed"
    limits = InvestigationLimits(
        max_rounds=5,
        finalization_rounds_reserved=3,
        max_finalization_invalid_json_retries=2,
        max_finalization_recovery_retries=1,
        max_total_tokens=32_000,
        max_total_prompt_chars=100_000,
    )
    investigator, provider = _investigator(
        [
            action_tool("search_repository", {"query": "provider", "mode": "content", "max_results": 5}),
            action_tool("graph_path", {"source": "module:main", "target": "module:providers.adapter", "max_depth": 2}),
            "not-json",
            json.dumps(invalid_envelope),
            final_action(evidence_id="E0002", source_reference=True),
        ],
        limits=limits,
    )

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["diagnosis"] is None
    assert report["stop_reason"] == "finalization_recovery_budget_exhausted"
    assert report["budget"]["model_rounds_used"] == 4
    assert report["budget"]["finalization_rejections_used"] == 2
    assert report["budget"]["max_finalization_recovery_retries"] == 1
    assert any(
        event.get("event") == "finalization_recovery_budget_exhausted"
        and event.get("reason_code") == "final_action_shape_invalid"
        for event in report["errors"]
    )
    assert "must-not-be-echoed" not in json.dumps({"messages": provider.messages, "report": report})


def test_finalization_context_is_rebuilt_with_exact_source_candidates_under_budget():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_total_tokens=32_000,
        max_total_prompt_chars=30_000,
        max_tool_context_chars=1_000,
    )
    investigator, provider = _investigator(
        [
            action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
            "not-json",
            final_action(evidence_id="E0002", source_reference=True),
        ],
        limits=limits,
    )

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["diagnosis"] is not None
    assert report["budget"]["finalization_context_rebuilds"] >= 1
    assert report["budget"]["finalization_context_target_exceeded"] is False
    assert report["budget"]["finalization_context_chars_after"] <= report["budget"]["finalization_context_target_chars"]
    finalization_turn = provider.messages[1]
    assert len(json.dumps(finalization_turn, sort_keys=True, separators=(",", ":"))) <= report["budget"]["finalization_context_target_chars"]
    payload = json.loads(finalization_turn[1]["content"])
    candidates = payload["source_reference_candidates"]
    assert any(
        item == {
            "evidence_id": "E0002",
            "path": SOURCE,
            "line": 2,
            "source_sha256": SOURCE_HASH,
        }
        for item in candidates
    )
    assert payload["evidence_ledger"][0]["evidence_id"] == "E0001"
    assert report["budget"]["model_rounds_used"] == 3


def test_finalization_compaction_drops_prior_raw_messages_but_keeps_latest_feedback():
    limits = InvestigationLimits(
        max_rounds=4,
        finalization_rounds_reserved=3,
        max_total_tokens=32_000,
        max_total_prompt_chars=100_000,
    )
    malformed = "very-large-untrusted-invalid-response-" + ("X" * 8_000)
    investigator, provider = _investigator(
        [
            action_tool("search_repository", {"query": "observed", "mode": "content", "max_results": 5}),
            malformed,
            final_action(evidence_id="E0002", source_reference=True),
        ],
        limits=limits,
    )

    report = investigator.run("Investigate a provider interface mismatch.")

    assert report["diagnosis"] is not None
    finalization_turn = provider.messages[2]
    serialized = json.dumps(finalization_turn)
    assert malformed not in serialized
    assert "invalid_strict_json" in serialized
    assert report["budget"]["finalization_context_rebuilds"] == 2

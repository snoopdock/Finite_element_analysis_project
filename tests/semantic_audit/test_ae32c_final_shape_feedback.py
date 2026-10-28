"""Regression tests for safe, field-level AE-32C final-schema feedback.

These tests use fake provider/evidence tools only; no live API is called.
"""
from __future__ import annotations

import hashlib
import json

from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator

SOURCE = "src/pkg/a.py"
SOURCE_BYTES = b"def run():\n    return 'observed'\n"
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
        else:
            result = {
                "query": arguments.get("query", ""),
                "matches": [{
                    "path": SOURCE,
                    "line": 2,
                    "match_kind": "content",
                    "snippet": "return 'observed'",
                    "source_sha256": SOURCE_HASH,
                }],
                "truncated": False,
            }
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
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "reported_cost_usd": 0.0,
        }

    def chat(self, messages, temperature=0.2, max_tokens=None, model=None):
        self.messages.append([dict(message) for message in messages])
        self.usage["prompt_tokens"] += 20
        self.usage["completion_tokens"] += 10
        self.usage["total_tokens"] += 30
        if not self.responses:
            return None, "fake provider response queue exhausted"
        return self.responses.pop(0), None

    def get_stats(self):
        return {"provider": self.provider_name, "model": self.model, "usage": dict(self.usage)}


def action_tool():
    return json.dumps({
        "action": "tool_call",
        "tool": "search_repository",
        "arguments": {"query": "observed", "mode": "content", "max_results": 5},
        "reason": "Find directly observed source evidence.",
    })


def final_action():
    source_ref = {
        "evidence_id": "E0002",
        "path": SOURCE,
        "line": 2,
        "source_sha256": SOURCE_HASH,
    }
    return {
        "action": "final",
        "diagnosis": {
            "summary": "A bounded interface-mismatch hypothesis based on observed evidence.",
            "root_cause": {
                "statement": "The consumer and provider may disagree on the counter attribute.",
                "confidence": "medium",
                "evidence_refs": ["E0002"],
                "source_references": [source_ref],
            },
            "claims": [{
                "statement": "The search result contains the inspected source line.",
                "kind": "observation",
                "confidence": "high",
                "evidence_refs": ["E0002"],
                "source_references": [source_ref],
            }],
            "proposed_corrective_action": "Inspect both interfaces and add a focused compatibility test.",
            "limitations": ["The fake evidence does not establish runtime behavior."],
            "next_steps": ["Review the provider contract and its caller."],
        },
    }


def run_investigation(responses, limits=None):
    provider = FakeProvider(responses)
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=FakeEvidenceTools(),
        limits=limits or InvestigationLimits(),
        id_factory=lambda: "test-final-shape-feedback",
    )
    return investigator.run("Investigate a failed workflow"), provider


def feedback_shapes(provider):
    found = []
    for turn in provider.messages:
        for message in turn:
            try:
                payload = json.loads(message.get("content", ""))
            except (TypeError, json.JSONDecodeError):
                continue
            feedback = payload.get("validation_feedback") if isinstance(payload, dict) else None
            if isinstance(feedback, dict) and isinstance(feedback.get("shape_diagnostics"), dict):
                found.append(feedback["shape_diagnostics"])
    return found


def test_extra_top_level_source_references_are_reported_without_values():
    malformed = final_action()
    malformed["source_references"] = [{"private_payload": "must-not-appear-in-report"}]
    good = final_action()
    report, provider = run_investigation([
        action_tool(),
        json.dumps(malformed),
        json.dumps(good),
    ])

    event = next(item for item in report["errors"] if item.get("event") == "final_action_rejected")
    assert event["shape_diagnostics"]["top_level"]["extra_keys"] == ["source_references"]
    assert "must-not-appear-in-report" not in json.dumps(report)
    assert any(
        item.get("top_level", {}).get("extra_keys") == ["source_references"]
        for item in feedback_shapes(provider)
    )


def test_root_cause_and_claim_key_mismatches_are_specific_and_value_free():
    malformed_root = final_action()
    malformed_root["diagnosis"]["root_cause"]["unexpected_root_key"] = "must-not-appear-in-report"

    malformed_claim = final_action()
    malformed_claim["diagnosis"]["claims"][0].pop("source_references")

    report, provider = run_investigation([
        action_tool(),
        json.dumps(malformed_root),
        json.dumps(malformed_claim),
        json.dumps(final_action()),
    ], limits=InvestigationLimits(
        max_invalid_final_attempts=3,
        max_finalization_recovery_retries=3,
    ))

    events = [
        item for item in report["errors"]
        if item.get("event") == "final_diagnosis_rejected"
    ]
    root_event = next(item for item in events if "root_cause_shape_invalid" in item["reason_codes"])
    claim_event = next(item for item in events if "claim_shape_invalid" in item["reason_codes"])

    assert root_event["shape_diagnostics"]["root_cause"]["extra_keys"] == ["unexpected_root_key"]
    assert claim_event["shape_diagnostics"]["claims"]["items"][0]["missing_keys"] == ["source_references"]
    assert "must-not-appear-in-report" not in json.dumps(report)

    shapes = feedback_shapes(provider)
    assert any(
        item.get("root_cause", {}).get("extra_keys") == ["unexpected_root_key"]
        for item in shapes
    )
    assert any(
        item.get("claims", {}).get("items", [{}])[0].get("missing_keys") == ["source_references"]
        for item in shapes
        if item.get("claims", {}).get("items")
    )

"""Deterministic fake-provider execution tests for the AE-45 C3 boundary.

These tests exercise the real RepositoryInvestigator lifecycle with local fake
providers. They do not construct a production provider, read credentials, or
perform network I/O.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.ae32c.investigator import (
    InvestigationError,
    InvestigationLimits,
    RepositoryInvestigator,
)
from tests.semantic_audit.test_ae32c_investigator import (
    SOURCE,
    SOURCE_BYTES,
    FakeEvidenceTools,
    FakeProvider,
    action_tool,
    final_action,
)


def _limits(**overrides):
    values = {
        "max_rounds": 3,
        "finalization_rounds_reserved": 1,
        "max_tool_calls": 4,
        "max_tokens_per_call": 2_048,
        "finalization_max_tokens_per_call": 6_144,
        "max_total_tokens": 30_720,
        "max_total_prompt_chars": 200_000,
        "max_elapsed_seconds": 30,
    }
    values.update(overrides)
    return InvestigationLimits(**values)


def test_fake_provider_completes_investigation_on_verified_retained_snapshot(tmp_path: Path):
    source = tmp_path / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(SOURCE_BYTES)
    evidence = RepositoryEvidenceTools(tmp_path)
    provider = FakeProvider([
        action_tool("read_source_file", {
            "path": SOURCE, "start_line": 1, "end_line": 2,
        }),
        final_action(evidence_id="E0002", source_reference=False),
    ])
    investigator = RepositoryInvestigator(
        tmp_path,
        provider,
        evidence_tools=evidence,
        limits=_limits(),
        id_factory=lambda: "ae45-c3-fake-provider-success",
    )

    report = investigator.run("Inspect the pinned source evidence.")

    assert report["diagnosis"] is not None
    assert report["snapshot_check_status"] == "verified"
    assert report["provenance"]["source_manifest_sha256"] == evidence.manifest_sha256
    assert report["provenance"]["graph_fingerprint"] == evidence.graph_fingerprint
    assert [item["tool"] for item in report["tool_calls"]] == [
        "repository_summary", "read_source_file",
    ]
    assert [item["evidence_id"] for item in report["evidence_ledger"]] == [
        "E0001", "E0002",
    ]
    assert provider.calls == 2
    assert report["budget"]["max_rounds"] == 3
    assert report["budget"]["max_tool_calls"] == 4
    assert report["execution_assessment"]["repository_code_executed"] is False
    assert report["execution_assessment"]["tests_executed_by_investigator"] is False
    assert report["execution_assessment"]["runtime_reproduction_status"] == "not_performed_read_only"
    with pytest.raises(InvestigationError, match="single_use"):
        investigator.run("A second invocation must be rejected.")


def test_tool_budget_exhaustion_stops_before_second_tool_dispatch():
    provider = FakeProvider([
        action_tool("search_repository", {
            "query": "observed", "mode": "content", "max_results": 5,
        }),
    ])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=evidence,
        limits=_limits(max_tool_calls=1),
        id_factory=lambda: "ae45-c3-fake-provider-tool-budget",
    )

    report = investigator.run("Exercise the tool-call budget boundary.")

    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "tool_call_budget_exhausted"
    assert provider.calls == 1
    assert [name for name, _ in evidence.calls] == ["repository_summary"]
    assert report["budget"]["tool_calls"] == 1
    assert report["budget"]["max_tool_calls"] == 1


def test_provider_failure_preserves_prior_evidence_and_terminates_without_success():
    provider = FakeProvider([
        action_tool("search_repository", {
            "query": "observed", "mode": "content", "max_results": 5,
        }),
        (None, "synthetic transport failure"),
    ])
    evidence = FakeEvidenceTools()
    investigator = RepositoryInvestigator(
        ".",
        provider,
        evidence_tools=evidence,
        limits=_limits(),
        id_factory=lambda: "ae45-c3-fake-provider-failure",
    )

    report = investigator.run("Exercise provider failure after evidence retrieval.")

    assert report["status"] == "incomplete"
    assert report["stop_reason"] == "provider_failure"
    assert provider.calls == 2
    assert [item["tool"] for item in report["tool_calls"]] == [
        "repository_summary", "search_repository",
    ]
    assert [item["evidence_id"] for item in report["evidence_ledger"]] == [
        "E0001", "E0002",
    ]
    assert report["investigation_continuity"]["evidence_preserved_after_provider_failure"] is True
    assert report["diagnosis"] is None

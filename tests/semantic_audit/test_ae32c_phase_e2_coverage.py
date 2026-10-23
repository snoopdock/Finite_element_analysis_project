"""AE-32C E.2: independent source-inspection coverage contracts.

A valid citation is not an inspection oracle. These tests distinguish searches,
partial reads, complete reads and direct, same-ledger root-cause citations.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32c import InvestigationLimits, RepositoryInvestigator
from tests.semantic_audit.test_ae32c_phase_e1_reliability import (
    FakeEvidenceTools, FakeProvider, action_tool,
)

A = "src/pkg/a.py"
B = "src/pkg/b.py"
A_BYTES = b"def run():\n    return 42\n"
B_BYTES = b"class Adapter:\n    calls = 0\n"
A_SHA = hashlib.sha256(A_BYTES).hexdigest()
B_SHA = hashlib.sha256(B_BYTES).hexdigest()


class CoverageEvidence(FakeEvidenceTools):
    def __init__(self, *, partial_b=False):
        super().__init__()
        self.file_hashes = {A: A_SHA, B: B_SHA}
        self.partial_b = partial_b

    def invoke(self, tool, arguments):
        if tool == "read_source_file":
            self.calls.append((tool, dict(arguments)))
            path = arguments["path"]
            if path not in self.file_hashes:
                return {"tool": tool, "status": "error", "error": {"code": "file_not_indexed"}, "provenance": self.provenance}
            source = A_BYTES if path == A else B_BYTES
            actual_lines = source.decode().splitlines()
            start = arguments.get("start_line", 1)
            if path == B and self.partial_b:
                start = 2
            end = len(actual_lines)
            return {"tool": tool, "status": "ok", "provenance": self.provenance,
                    "result": {"path": path, "source_sha256": self.file_hashes[path],
                               "start_line": start, "end_line": end,
                               "total_lines": len(actual_lines),
                               "requested_end_line": 100, "truncated": True,
                               "content": "\n".join(f"{i}: {actual_lines[i-1]}" for i in range(start, end + 1))}}
        if tool == "search_repository":
            self.calls.append((tool, dict(arguments)))
            return {"tool": tool, "status": "ok", "provenance": self.provenance,
                    "result": {"query": arguments["query"], "matches": [{
                        "path": A, "source_sha256": A_SHA, "line": 1,
                        "match_kind": "content", "snippet": "def run():"
                    }], "truncated": False}}
        return super().invoke(tool, arguments)


def final(*, confidence="high", a_evidence="E0002", b_evidence="E0003", include_b=True):
    refs = [{"evidence_id": a_evidence, "path": A, "line": 1, "source_sha256": A_SHA}]
    evidence_ids = [a_evidence]
    if include_b:
        refs.append({"evidence_id": b_evidence, "path": B, "line": 1, "source_sha256": B_SHA})
        evidence_ids.append(b_evidence)
    diagnosis = {
        "summary": "Static interface evidence supports a possible mismatch, not runtime proof.",
        "root_cause": {"statement": "The observed source may have mismatched attributes.",
                       "confidence": confidence, "evidence_refs": evidence_ids,
                       "source_references": refs},
        "claims": [{"statement": "Source lines were observed.", "kind": "observation",
                    "confidence": "medium", "evidence_refs": evidence_ids,
                    "source_references": refs}],
        "proposed_corrective_action": "Inspect the call contract.",
        "limitations": ["No runtime reproduction was run."],
        "next_steps": ["Confirm the provider interface experimentally."],
    }
    return json.dumps({"action": "final", "diagnosis": diagnosis})


def execute(responses, *, partial_b=False, required=(A, B), rounds=5, reserved=2):
    fake = CoverageEvidence(partial_b=partial_b)
    provider = FakeProvider(responses)
    runner = RepositoryInvestigator(
        ".", provider, evidence_tools=fake, required_source_paths=required,
        limits=InvestigationLimits(max_rounds=rounds, finalization_rounds_reserved=reserved,
                                   max_total_tokens=100_000, max_total_prompt_chars=190_000),
        id_factory=lambda: "coverage-regression",
    )
    return runner.run("Review the declared interface boundary"), provider, runner


def read(path):
    return action_tool("read_source_file", {"path": path, "start_line": 1, "end_line": 100})


def test_full_direct_reads_support_high_confidence_with_both_bound_citations():
    report, _, _ = execute([read(A), read(B), final()])
    assert report["status"] == "completed_with_incomplete_evidence", report
    assert report["snapshot_check_status"] == "not_available_for_injected_evidence_adapter"
    coverage = report["required_source_coverage"]
    assert coverage["status"] == "complete"
    assert coverage["complete_read_paths"] == [A, B]
    assert coverage["root_cause_direct_citation_paths"] == [A, B]
    assert not coverage["missing_complete_reads"]
    assert not coverage["missing_root_cause_direct_citations"]
    assert report["diagnosis_assurance"] == "references_resolved_not_independently_proven"


def test_medium_diagnosis_with_missing_required_read_is_explicitly_incomplete():
    report, _, _ = execute([read(A), final(confidence="medium", include_b=False)], rounds=3, reserved=1)
    assert report["status"] == "completed_with_incomplete_evidence", report
    assert report["stop_reason"] == "diagnosis_submitted_with_required_source_coverage_gap"
    assert report["required_source_coverage"]["missing_complete_reads"] == [B]
    assert report["diagnosis_assurance"] == "references_resolved_required_source_coverage_incomplete"


def test_high_confidence_rejected_when_required_source_not_inspected():
    report, _, _ = execute([read(A), final(include_b=False)], rounds=3, reserved=1)
    assert report["diagnosis"] is None
    assert report["status"] != "completed"
    assert any("high_confidence_required_source_coverage_incomplete" in ev.get("reason_codes", [])
               for ev in report["errors"])


def test_partial_file_read_is_not_complete_evidence():
    # Read of B starts at line 2 even though a matched line remains available.
    report, _, _ = execute([read(A), read(B), final(confidence="medium", include_b=False)], partial_b=True)
    assert report["status"] == "completed_with_incomplete_evidence", report
    assert report["required_source_coverage"]["missing_complete_reads"] == [B]


def test_search_result_cannot_impersonate_source_read():
    report, _, _ = execute([
        action_tool("search_repository", {"query": "interface", "mode": "content", "max_results": 5}),
        final(confidence="medium", include_b=False, a_evidence="E0002"),
    ], rounds=3, reserved=1)
    assert report["status"] == "completed_with_incomplete_evidence", report
    assert report["required_source_coverage"]["direct_read_paths"] == []


@pytest.mark.parametrize("paths", [
    ("../src/pkg/a.py",), ("/tmp/attack.py",), ("src\\pkg\\a.py",),
    ("src/pkg/missing.py",), ("src/pkg/a.py",) * 13, (17,),
])
def test_invalid_critical_path_policy_rejected_before_model_call(paths):
    with pytest.raises(ValueError):
        RepositoryInvestigator(".", FakeProvider([]), evidence_tools=CoverageEvidence(),
                               required_source_paths=paths)


def test_no_requirement_preserves_previous_contract():
    report, _, _ = execute([read(A), final(confidence="medium", include_b=False)],
                           required=(), rounds=3, reserved=1)
    assert report["status"] == "completed_with_incomplete_evidence", report
    assert report["required_source_coverage"]["status"] == "not_configured"

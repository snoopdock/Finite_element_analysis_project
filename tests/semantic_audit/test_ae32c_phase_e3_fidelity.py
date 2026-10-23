"""E.3 regression oracles: EOF clamp != omission, protocol != assurance."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
from audit_engine.semantic_audit.ae32c.batch_evaluation import (
    PROVIDERS, build_summary, evaluate_trial, trial_sequence,
)
from tests.semantic_audit.test_ae32c_phase_e2_coverage import (
    A, B, execute, final, read,
)


def test_eof_clamp_does_not_mean_omitted_source_lines(tmp_path: Path):
    (tmp_path / "tiny.py").write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")
    tools = RepositoryEvidenceTools(tmp_path)
    result = tools.invoke("read_source_file", {"path": "tiny.py", "start_line": 1, "end_line": 999})
    assert result["status"] == "ok", result
    data = result["result"]
    assert data["truncated"] is True  # historical compatibility
    assert data["end_clamped_to_eof"] is True
    assert data["content_omitted"] is False
    assert data["omitted_line_count"] == 0
    assert data["read_coverage"] == "complete_file"
    assert data["source_range_complete"] is True
    assert (data["start_line"], data["end_line"], data["total_lines"]) == (1, 2, 2)
    assert data["source_sha256"] == tools.file_hashes["tiny.py"]


def test_partial_source_read_remains_incomplete_even_when_end_is_clamped(tmp_path: Path):
    (tmp_path / "tiny.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    data = RepositoryEvidenceTools(tmp_path).invoke("read_source_file", {
        "path": "tiny.py", "start_line": 2, "end_line": 50,
    })["result"]
    assert data["end_clamped_to_eof"] is True
    assert data["content_omitted"] is True
    assert data["source_range_complete"] is False
    assert data["read_coverage"] == "partial_file"
    assert data["omitted_line_count"] == 1


def test_max_read_char_limit_cannot_claim_full_source(tmp_path: Path):
    (tmp_path / "large.py").write_text("\n".join(f"x_{i} = '{'A'*180}'" for i in range(90)) + "\n", encoding="utf-8")
    result = RepositoryEvidenceTools(tmp_path).invoke("read_source_file", {
        "path": "large.py", "start_line": 1, "end_line": 999,
    })
    assert result["status"] == "ok"
    data = result["result"]
    assert data["content_omitted"] is True
    assert data["source_range_complete"] is False
    assert data["omitted_line_count"] > 0
    assert data["end_line"] < data["total_lines"]


def test_empty_source_is_explicitly_empty(tmp_path: Path):
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    data = RepositoryEvidenceTools(tmp_path).invoke("read_source_file", {"path": "empty.py", "end_line": 90})["result"]
    assert data["read_coverage"] == "empty_file"
    assert data["source_range_complete"] is True
    assert data["content_omitted"] is False
    assert data["total_lines"] == 0


def test_investigator_emits_last_evidence_round_coverage_guidance():
    report, provider, _ = execute([read(A), final(confidence="medium", include_b=False)],
                                  rounds=4, reserved=2)
    assert report["status"] == "completed_with_incomplete_evidence"
    reminders = [event for event in report["errors"] if event.get("event") == "required_source_read_reminder"]
    assert reminders and reminders[0]["missing_path_count"] == 1
    guidance = [m["content"] for message_batch in provider.messages for m in message_batch
                if "evidence_inspection_reminder" in m["content"]]
    assert guidance
    assert json.loads(guidance[-1])["evidence_inspection_reminder"]["missing_complete_source_reads"] == [B]


def _make_trial(root: Path, round_number: int, provider: str, *, coverage="complete", status="completed", exit_code=0):
    path = root / f"round-{round_number:02d}" / provider
    path.mkdir(parents=True)
    (path / "runner-exit-code.txt").write_text(str(exit_code) + "\n", encoding="utf-8")
    comparison = {
        "provider": provider, "baseline": {"status": "completed"},
        "graph_assisted": {
            "summary": {"status": status, "model_rounds": 6, "tool_call_count": 4,
                        "final_citation_validation": "references_resolved",
                        "stop_reason": "diagnosis_submitted"},
            "report": {"snapshot_check_status": "verified", "elapsed_seconds": 4.5,
                       "source_textual_support": {"status": "complete", "declared_anchor_count": 2, "missing_direct_cited_anchors": []},
                       "required_source_coverage": {"status": coverage,
                         "missing_complete_reads": [] if coverage == "complete" else ["providers/adapter.py"],
                         "missing_root_cause_direct_citations": []}},
        },
    }
    output = path / "ae32c-evaluation-test"
    output.mkdir()
    data = json.dumps(comparison, sort_keys=True) + "\n"
    (output / "comparison.json").write_text(data, encoding="utf-8")
    md = "# Test comparison fixture\n"
    (output / "comparison.md").write_text(md, encoding="utf-8")
    (output / "SHA256SUMS.txt").write_text(
        hashlib.sha256(data.encode()).hexdigest() + "  comparison.json\n" +
        hashlib.sha256(md.encode()).hexdigest() + "  comparison.md\n", encoding="ascii")
    return path


def test_batch_round_robin_order_is_deterministic():
    assert trial_sequence(2) == [(1, provider) for provider in PROVIDERS] + [(2, provider) for provider in PROVIDERS]
    with pytest.raises(ValueError):
        trial_sequence(5)
    with pytest.raises(ValueError):
        trial_sequence(True)


def test_batch_full_coverage_requires_every_trial(tmp_path: Path):
    for round_number, provider in trial_sequence(2):
        _make_trial(tmp_path, round_number, provider)
    summary = build_summary(tmp_path, 2)
    assert summary["passed"] is True
    assert summary["expected_trials"] == 6
    assert summary["protocol_completed"] == 6
    assert summary["evidence_complete"] == 6
    assert [(r["round"],r["provider"]) for r in summary["trials"]] == trial_sequence(2)


def test_batch_never_counts_incomplete_accepted_diagnosis_as_evidence_complete(tmp_path: Path):
    path = _make_trial(tmp_path, 1, "cloudflare", status="completed_with_incomplete_evidence", coverage="incomplete")
    row = evaluate_trial(path, round_number=1, provider="cloudflare")
    assert row["protocol_complete"] is True
    assert row["evidence_complete"] is False
    assert row["passed"] is False
    assert "required_source_evidence_incomplete" in row["issues"]


def test_batch_preserves_other_trials_after_one_failure(tmp_path: Path):
    for round_number, provider in trial_sequence(1):
        _make_trial(tmp_path, round_number, provider, exit_code=1 if provider == "nararouter" else 0)
    summary = build_summary(tmp_path, 1)
    assert summary["expected_trials"] == 3
    assert summary["observed_trials"] == 3
    assert summary["evidence_complete"] == 2
    assert summary["passed"] is False
    assert summary["trials"][2]["passed"] is True


def test_batch_missing_expected_trial_fails_closed(tmp_path: Path):
    _make_trial(tmp_path, 1, "cloudflare")
    summary = build_summary(tmp_path, 1)
    assert summary["expected_trials"] == 3
    assert summary["observed_trials"] == 1
    assert summary["passed"] is False

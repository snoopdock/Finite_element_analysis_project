"""AE-32C Patch 1 adversarial tests for evidence integrity and sanitization.

These tests are intended for GitHub Actions validation. They are not executed
while preparing the patch, per the requested validation workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32b import RepositoryEvidenceTools


def _write(root: Path, relative: str, text: str | bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def _minimal_repo(root: Path) -> Path:
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/a.py", "from . import b\n\ndef target():\n    return b.value\n")
    _write(root, "src/pkg/b.py", "value = 1\n")
    _write(root, "tests/test_a.py", "from src.pkg.a import target\n\ndef test_target():\n    assert target() == 1\n")
    return root


def test_graph_tool_response_nested_mutation_cannot_change_internal_graph(tmp_path):
    server = RepositoryEvidenceTools(_minimal_repo(tmp_path))
    original_fingerprint = server.graph_fingerprint
    first = server.invoke("graph_neighbors", {
        "node": "module:src.pkg.a", "direction": "both", "max_depth": 1,
    })
    assert first["status"] == "ok"
    candidate = next((node for node in first["result"].get("source_nodes", [])
                      if isinstance(node.get("paths"), list)), None)
    if candidate is None:
        candidate = next((node for node in first["result"].get("discovered_nodes", [])
                          if isinstance(node.get("paths"), list)), None)
    assert candidate is not None
    candidate["paths"].append("fabricated/outside.py")
    assert server._graph_fingerprint() == original_fingerprint
    second = server.invoke("graph_neighbors", {
        "node": "module:src.pkg.a", "direction": "both", "max_depth": 1,
    })
    assert second["provenance"]["graph_fingerprint"] == original_fingerprint
    assert "fabricated/outside.py" not in json.dumps(second, ensure_ascii=False)


def test_long_secret_assignment_is_redacted_before_snippet_truncation(tmp_path):
    root = _minimal_repo(tmp_path)
    synthetic_secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    _write(root, "config.yaml", 'api_token: "' + synthetic_secret + "X" * 600 + '"\n')
    server = RepositoryEvidenceTools(root)
    response = server.invoke("search_repository", {"query": "api_token", "mode": "content"})
    assert response["status"] == "ok"
    assert synthetic_secret not in json.dumps(response, ensure_ascii=False)
    assert "<redacted>" in json.dumps(response, ensure_ascii=False)


def test_secret_shaped_structured_status_is_redacted_in_graph_output(tmp_path):
    root = _minimal_repo(tmp_path)
    synthetic_secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    _write(
        root,
        "decision_memory/rules/RULE-1.yaml",
        f"id: RULE-1\nstatus: '{synthetic_secret}'\nstatement: safe test record\n",
    )
    server = RepositoryEvidenceTools(root)
    response = server.invoke("graph_neighbors", {
        "node": "decision_record:rule:RULE-1", "direction": "both", "max_depth": 1,
    })
    assert response["status"] == "ok"
    serialized = json.dumps(response, ensure_ascii=False, allow_nan=False)
    assert synthetic_secret not in serialized
    assert "<redacted-token>" in serialized or "<redacted>" in serialized


def test_recursive_yaml_alias_is_quarantined_and_marks_index_incomplete(tmp_path):
    root = _minimal_repo(tmp_path)
    _write(
        root,
        "decision_memory/rules/RULE-CYCLE.yaml",
        "id: RULE-CYCLE\nreview: &review\n  approved: *review\nstatus: test\nstatement: cyclic fixture\n",
    )
    server = RepositoryEvidenceTools(root)
    summary = server.invoke("repository_summary", {})
    assert summary["status"] == "ok"
    assert summary["result"]["evidence_index_status"] == "incomplete"
    assert any(issue["code"] == "recursive_value" for issue in summary["result"]["structured_record_issues"])
    json.dumps(summary, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("scalar", [".nan", ".inf", "2026-10-19"])
def test_yaml_nonfinite_and_date_scalars_remain_strict_json_compatible(tmp_path, scalar):
    root = _minimal_repo(tmp_path)
    _write(
        root,
        "decision_memory/rules/RULE-VALUE.yaml",
        f"id: RULE-VALUE\nreview:\n  approved: {scalar}\nstatus: test\nstatement: scalar fixture\n",
    )
    server = RepositoryEvidenceTools(root)
    summary = server.invoke("repository_summary", {})
    assert summary["status"] == "ok"
    json.dumps(summary, ensure_ascii=False, allow_nan=False)
    if scalar in {".nan", ".inf"}:
        assert summary["result"]["evidence_index_status"] == "incomplete"
        assert any(issue["code"] == "non_finite_number_normalized"
                   for issue in summary["result"]["structured_record_issues"])


def test_duplicate_decision_record_ids_are_reported_not_silently_merged(tmp_path):
    root = _minimal_repo(tmp_path)
    _write(root, "decision_memory/rules/RULE-DUP.yaml", "id: RULE-DUP\nstatus: first\nstatement: first record\n")
    _write(root, "decision_memory/rules/RULE-DUP-copy.yaml", "id: RULE-DUP\nstatus: second\nstatement: second record\n")
    server = RepositoryEvidenceTools(root)
    summary = server.invoke("repository_summary", {})
    assert summary["result"]["evidence_index_status"] == "incomplete"
    assert any(issue["code"] == "duplicate_record_identity"
               for issue in summary["result"]["structured_record_issues"])


def test_unreadable_utf8_source_marks_evidence_index_incomplete(tmp_path):
    root = _minimal_repo(tmp_path)
    _write(root, "notes.md", b"valid prefix\xff invalid utf8\n")
    server = RepositoryEvidenceTools(root)
    summary = server.invoke("repository_summary", {})
    assert summary["status"] == "ok"
    assert summary["result"]["skipped_non_utf8_file_count"] == 1
    assert summary["result"]["evidence_index_status"] == "incomplete"
    assert summary["provenance"]["evidence_index_status"] == "incomplete"

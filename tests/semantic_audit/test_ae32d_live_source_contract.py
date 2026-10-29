"""AE-32D: source contract selection cannot inherit the wrong incident witnesses.

These tests do not call live providers or execute untrusted repository code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32c import live_evaluation


def test_original_incident_keeps_existing_strict_source_requirements():
    root = Path("tests/semantic_audit/fixtures/ae32c_provider_interface_incident")
    paths, anchors = live_evaluation._required_source_contract(
        root, [], [], {"pipeline/extractor.py", "providers/adapter.py"})
    assert paths == ("pipeline/extractor.py", "providers/adapter.py")
    assert anchors == {
        "pipeline/extractor.py": ("provider.total_calls",),
        "providers/adapter.py": ("self.calls",),
    }


def test_second_incident_gets_only_its_own_declared_witnesses():
    root = Path("tests/semantic_audit/fixtures/ae32d_branch_unbound_incident")
    paths, anchors = live_evaluation._required_source_contract(
        root,
        ["branch_logic.py"],
        ["branch_logic.py::if flag:", "branch_logic.py::return result"],
        {"branch_logic.py"},
    )
    assert paths == ("branch_logic.py",)
    assert anchors == {"branch_logic.py": ("if flag:", "return result")}
    assert "providers/adapter.py" not in anchors


def test_unknown_fixture_has_no_legacy_incident_witnesses():
    paths, anchors = live_evaluation._required_source_contract(
        Path("arbitrary_fixture"), [], [], {"other.py"})
    assert paths == () and anchors == {}


@pytest.mark.parametrize("paths,anchors,index,reason", [
    (["branch_logic.py"], ["providers/adapter.py::self.calls"], {"branch_logic.py"}, "declared_source_anchor_path_not_required"),
    (["branch_logic.py"], ["branch_logic.py::if flag:"], {"different.py"}, "declared_source_path_not_in_snapshot"),
    (["../secret.py"], [], {"../secret.py"}, "invalid_declared_source_path"),
    (["branch_logic.py"], ["branch_logic.py"], {"branch_logic.py"}, "invalid_declared_source_anchor_format"),
    (["branch_logic.py", "branch_logic.py"], [], {"branch_logic.py"}, "duplicate_declared_source_path"),
])
def test_invalid_source_contracts_fail_closed(paths, anchors, index, reason):
    with pytest.raises(ValueError, match=reason):
        live_evaluation._required_source_contract(Path("case"), paths, anchors, index)


def test_second_incident_contract_works_before_any_live_calls(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    fixture = checkout / "tests/semantic_audit/fixtures/ae32d_branch_unbound_incident"
    fixture.mkdir(parents=True)
    (fixture / "branch_logic.py").write_text(
        "def work(flag):\n    if flag:\n        result = 5\n    return result\n",
        encoding="utf-8",
    )
    outside = tmp_path / "output"
    outside.mkdir()
    monkeypatch.chdir(checkout)
    seen = []

    class FakeProvider:
        model = "offline-test-model"

        def chat(self, *args, **kwargs):
            return "no diagnosis", None

        def get_stats(self):
            return {"usage": {}}

    class FakeInvestigator:
        def __init__(self, *args, **kwargs):
            seen.append(kwargs)

        def run(self, *args):
            return {"status": "incomplete", "stop_reason": "no_scripted_diagnosis",
                    "tool_calls": [], "model_actions": [], "evidence_ledger": []}

    monkeypatch.setattr(live_evaluation, "_build_provider", lambda *a, **k: FakeProvider())
    monkeypatch.setattr(live_evaluation, "RepositoryInvestigator", FakeInvestigator)
    status = live_evaluation.main([
        "--confirm-live-provider-calls", "--provider", "cloudflare",
        "--repo-root", str(fixture),
        "--output-dir", str(outside),
        "--baseline-context-path", "branch_logic.py",
        "--required-source-path", "branch_logic.py",
        "--required-source-anchor", "branch_logic.py::if flag:",
        "--required-source-anchor", "branch_logic.py::return result",
        "--problem", "Investigate work(False).",
    ])
    assert status == 0
    assert len(seen) == 1
    assert seen[0]["required_source_paths"] == ("branch_logic.py",)
    assert seen[0]["required_source_anchors"] == {
        "branch_logic.py": ("if flag:", "return result")
    }
    report = json.loads(next(outside.rglob("comparison.json")).read_text())
    assert report["graph_assisted"]["summary"]["stop_reason"] != "graph_assisted_initialization_failed"


def test_real_investigator_accepts_second_incident_contract():
    from audit_engine.semantic_audit.ae32b.evidence_tools import RepositoryEvidenceTools
    from audit_engine.semantic_audit.ae32c.investigator import RepositoryInvestigator

    root = Path("tests/semantic_audit/fixtures/ae32d_branch_unbound_incident")
    tools = RepositoryEvidenceTools(root)
    paths, anchors = live_evaluation._required_source_contract(
        root,
        ["branch_logic.py"],
        ["branch_logic.py::if flag:", "branch_logic.py::return result"],
        set(tools.contents),
    )
    engine = RepositoryInvestigator(root, object(), evidence_tools=tools,
                                     required_source_paths=paths,
                                     required_source_anchors=anchors)
    assert engine._required_source_paths == ("branch_logic.py",)
    assert engine._required_source_anchors == {
        "branch_logic.py": ("if flag:", "return result")
    }

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae32a.audit import audit_repository


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(root: Path) -> Path:
    _write(root, "audit_engine/semantic_audit/ae01/__init__.py", "")
    _write(root, "audit_engine/semantic_audit/ae01/pipeline.py", "from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService\n")
    _write(root, "audit_engine/semantic_audit/graph/__init__.py", "from .service import SemanticGraphAnalysisService\n")
    _write(root, "audit_engine/semantic_audit/graph/service.py", "class SemanticGraphAnalysisService:\n    pass\n")
    _write(root, "audit_engine/semantic_audit/ae28/__init__.py", "")
    _write(root, "audit_engine/semantic_audit/ae28/adapter.py", "def verify_interpretation(value):\n    return value\ndef ingest_model_response(value):\n    return verify_interpretation(value)\n")
    _write(root, "audit_engine/semantic_audit/ae29/__init__.py", "")
    _write(root, "audit_engine/semantic_audit/ae29/controller.py", "from audit_engine.semantic_audit.ae28.adapter import verify_interpretation\ndef validate_verification(receipt):\n    return receipt\ndef evaluate_iteration(receipt):\n    return validate_verification(receipt)\n")
    _write(root, "audit_engine/semantic_audit/ae30/__init__.py", "")
    _write(root, "audit_engine/semantic_audit/ae30/evaluator.py", "from audit_engine.semantic_audit.ae29.controller import verify_interpretation\nexpected = 'pass'\nactual = 'pass'\n")
    _write(root, "audit_engine/semantic_audit/ae31/__init__.py", "")
    _write(root, "audit_engine/semantic_audit/ae31/__main__.py", "")
    _write(root, "audit_engine/semantic_audit/ae31/diagnosis.py", '''import requests
INPUT_PATHS = ("src/a.py", "tests/test_a.py")
BASE_URL = "https://router.example/v1"
def diagnose():
    return requests.post(BASE_URL + "/chat/completions", json={"messages": []})
''')
    _write(root, "tests/semantic_audit/test_ae31_diagnosis.py", "from audit_engine.semantic_audit.ae31 import diagnosis\n")
    _write(root, "main.py", "from providers.factory import create_provider\n")
    _write(root, "providers/factory.py", "def create_provider():\n    return None\n")
    _write(root, ".github/workflows/fea.yml", "name: FEA\non:\n  workflow_dispatch:\njobs:\n  run:\n    steps:\n      - run: python main.py --config config.yaml\n")
    _write(root, "config.yaml", "mode: test\n")
    return root


def test_discovers_components_and_keeps_test_presence_separate_from_production_consumers(tmp_path):
    root = _fixture(tmp_path)
    report = audit_repository(root)
    components = {item["component"]: item for item in report["components"]}
    assert {"ae01", "ae28", "ae29", "ae30", "ae31"} <= set(components)
    assert components["ae31"]["test_presence"] is True
    assert components["ae31"]["production_consumer_presence"] is False
    assert components["ae29"]["audit_chain_consumer_presence"] is True
    assert components["ae30"]["audit_chain_consumer_presence"] is False
    assert components["ae01"]["graph_api_evidence"]


def test_detects_llm_http_without_tool_loop_or_graph_query(tmp_path):
    report = audit_repository(_fixture(tmp_path))
    components = {item["component"]: item for item in report["components"]}
    ae31 = components["ae31"]
    assert ae31["llm_transport_evidence"]
    assert ae31["fixed_allowlist_evidence"]
    assert ae31["graph_api_evidence"] == []
    assert ae31["exposed_as_llm_tool_evidence"] == []
    finding_ids = {item["id"] for item in report["findings"]}
    assert "AE32A-LLM-ISOLATION-AE31" in finding_ids
    assert "AE32A-NO-TOOL-LOOP" in finding_ids
    assert "AE32A-FIXED-DIAGNOSTIC-CONTEXT" in finding_ids
    assert "AE32A-AE28-EXTERNAL-MODEL-INPUT" in finding_ids
    assert "AE32A-AE29-VERIFICATION-RECEIPT-ONLY" in finding_ids


def test_resolves_internal_imports_and_workflow_commands(tmp_path):
    report = audit_repository(_fixture(tmp_path))
    assert any(edge["source"] == "audit_engine.semantic_audit.ae29.controller"
               and edge["target"] == "audit_engine.semantic_audit.ae28.adapter"
               for edge in report["python_import_edges"])
    assert any(edge["kind"] == "workflow_invokes_script" and edge["target"] == "main.py"
               for edge in report["workflow_edges"])
    assert report["system_components"]["workflow_invokes_ae_cli"] is False


def test_report_output_is_atomic_deterministic_and_excluded_from_own_manifest(tmp_path):
    root = _fixture(tmp_path)
    output = root / "artifacts" / "audit_engine" / "ae32a"
    first = audit_repository(root, output_dir=output)
    first_bytes = (output / "architecture_wiring_report.json").read_bytes()
    second = audit_repository(root, output_dir=output)
    second_bytes = (output / "architecture_wiring_report.json").read_bytes()
    assert first["audit"]["manifest_sha256"] == second["audit"]["manifest_sha256"]
    assert first_bytes == second_bytes
    assert json.loads(first_bytes)["summary"]["runtime_execution_performed"] is False
    assert json.loads(first_bytes)["summary"]["report_artifacts_written"] is True
    assert (output / "execution_dependency_map.mmd").is_file()


def test_invalid_python_makes_scan_incomplete_instead_of_clean(tmp_path):
    root = _fixture(tmp_path)
    _write(root, "audit_engine/semantic_audit/ae31/broken.py", "def incomplete(:\n")
    report = audit_repository(root)
    assert report["audit"]["status"] == "incomplete"
    assert any(issue["path"].endswith("broken.py") for issue in report["python_parse_issues"])
    assert "AE32A-INCOMPLETE-PYTHON-SCAN" in {item["id"] for item in report["findings"]}


def test_symlinked_source_is_excluded_and_reported(tmp_path):
    root = _fixture(tmp_path / "repo")
    outside = tmp_path / "outside.py"
    outside.write_text("password = 'must-not-be-read'\n", encoding="utf-8")
    link = root / "audit_engine/semantic_audit/ae31/linked.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported by this environment")
    report = audit_repository(root)
    assert any(issue["path"].endswith("linked.py") and issue["kind"] == "symlink_file_excluded"
               for issue in report["scope_issues"])
    serialized = json.dumps(report)
    assert "must-not-be-read" not in serialized
    assert report["audit"]["status"] == "incomplete"


def test_output_path_outside_root_is_rejected(tmp_path):
    root = _fixture(tmp_path / "repo")
    with pytest.raises(ValueError, match="inside the audited repository"):
        audit_repository(root, output_dir=tmp_path / "outside")


def test_report_does_not_claim_test_passes_or_live_execution(tmp_path):
    report = audit_repository(_fixture(tmp_path))
    assert report["summary"]["runtime_execution_performed"] is False
    assert report["summary"]["network_calls_performed"] is False
    assert report["summary"]["authoritative_source_files_modified"] is False
    assert report["summary"]["report_artifacts_written"] is False
    assert all("test_passed" not in component for component in report["components"])


def test_tool_loop_requires_both_model_protocol_and_dispatch_evidence(tmp_path):
    root = _fixture(tmp_path)
    report_without_loop = audit_repository(root)
    assert "AE32A-NO-TOOL-LOOP" in {item["id"] for item in report_without_loop["findings"]}
    _write(root, "audit_engine/semantic_audit/ae31/diagnosis.py", '''import requests
INPUT_PATHS = ("src/a.py",)
BASE_URL = "https://router.example/v1"
def diagnose(response):
    tool_calls = response["tool_calls"]
    return execute_tool(tool_calls[0]["name"])
def execute_tool(name):
    return {"tool": name}
def call_model():
    return requests.post(BASE_URL + "/chat/completions", json={"tools": []})
''')
    report_with_loop = audit_repository(root)
    components = {item["component"]: item for item in report_with_loop["components"]}
    assert components["ae31"]["exposed_as_llm_tool_evidence"]
    assert "AE32A-NO-TOOL-LOOP" not in {item["id"] for item in report_with_loop["findings"]}


def test_source_and_runner_revision_are_explicit_provenance_not_inferred(tmp_path):
    root = _fixture(tmp_path)
    report = audit_repository(root, source_revision="a" * 40, runner_revision="b" * 40)
    assert report["audit"]["source_revision"] == "a" * 40
    assert report["audit"]["runner_revision"] == "b" * 40
    unknown = audit_repository(root)
    assert unknown["audit"]["source_revision"] is None
    assert unknown["audit"]["runner_revision"] is None


def test_scanner_never_executes_inspected_python(tmp_path):
    root = _fixture(tmp_path)
    _write(root, "src/side_effect.py", "from pathlib import Path\nPath('executed-by-audit').write_text('no')\nraise RuntimeError('must not execute')\n")
    report = audit_repository(root)
    assert report["audit"]["status"] == "complete"
    assert not (root / "executed-by-audit").exists()


def test_total_byte_budget_marks_scan_incomplete(monkeypatch, tmp_path):
    from audit_engine.semantic_audit.ae32a import audit as audit_module

    root = _fixture(tmp_path)
    monkeypatch.setattr(audit_module, "MAX_TOTAL_BYTES", 128)
    report = audit_module.audit_repository(root)
    assert report["audit"]["status"] == "incomplete"
    assert any(issue["kind"] == "total_source_byte_budget_exceeded" for issue in report["scope_issues"])


def test_nested_workflow_is_reported_but_not_counted_as_active(tmp_path):
    root = _fixture(tmp_path)
    _write(root, ".github/workflows/archive/old.yml", "name: archived\non:\n  workflow_dispatch:\njobs: {}\n")
    report = audit_repository(root)
    assert report["audit"]["workflow_count"] == 1
    assert report["audit"]["archived_nested_workflow_count"] == 1
    assert not any(edge["source"].endswith("archive/old.yml") for edge in report["workflow_edges"])


def test_invalid_revision_metadata_is_rejected(tmp_path):
    root = _fixture(tmp_path)
    with pytest.raises(ValueError, match="hexadecimal Git revision"):
        audit_repository(root, source_revision="not-a-commit")

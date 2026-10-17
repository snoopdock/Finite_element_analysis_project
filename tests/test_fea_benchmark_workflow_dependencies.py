from pathlib import Path


def test_fea_benchmark_source_validation_installs_jsonschema_before_pytest():
    repository_root = Path(__file__).resolve().parents[1]
    workflow_path = repository_root / ".github" / "workflows" / "FEA-llm-provider-benchmark.yml"
    assert workflow_path.is_file(), "benchmark workflow candidate must exist on the validation branch"
    workflow = workflow_path.read_text(encoding="utf-8")

    start = workflow.index("  validate-source:")
    end = workflow.index("\n  benchmark:", start)
    validate_source = workflow[start:end]

    install = "python -m pip install 'jsonschema>=4.20,<5'"
    assert install in validate_source
    assert validate_source.index("pip install -r requirements.txt") < validate_source.index(install)
    assert validate_source.index(install) < validate_source.index("pytest -q")


def test_fea_benchmark_workflow_remains_manual_and_read_only():
    repository_root = Path(__file__).resolve().parents[1]
    workflow_path = repository_root / ".github" / "workflows" / "FEA-llm-provider-benchmark.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "\npermissions:\n  contents: read\n" in workflow
    assert "\npush:" not in workflow
    assert "\npull_request:" not in workflow

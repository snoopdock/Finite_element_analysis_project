import json

from scripts.fea_provider_benchmark_report import build_summary, render_markdown


def test_benchmark_summary_captures_provider_usage_and_artifact_hashes(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "output").mkdir()
    state = {
        "model_usage": {
            "provider": "openrouter",
            "model": "deepseek/test",
            "logical_calls": 3,
            "successful_calls": 2,
            "failed_calls": 1,
            "http_attempts": 4,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        },
        "last_run_status": "partial",
        "cycle": 1,
        "iteration": 1,
    }
    (tmp_path / "state" / "current_state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "output" / "guideline.tex").write_text("\\documentclass{article}", encoding="utf-8")
    (tmp_path / "output" / "validation_report.md").write_text("## Errors\n- model failure", encoding="utf-8")

    summary = build_summary(tmp_path, {
        "provider": "openrouter",
        "model": "deepseek/test",
        "target_branch": "stage1/section-uuids",
        "commit": "abc123",
        "max_tokens_per_call": 8000,
        "max_llm_calls": 80,
        "pipeline_outcome": "success",
        "publication_outcome": "failure",
    })
    assert summary["model_usage"]["usage"]["total_tokens"] == 150
    assert summary["benchmark"]["pipeline_status"] == "success"
    assert summary["benchmark"]["publication_status"] == "failed"
    tex = next(item for item in summary["artifacts"] if item["path"] == "output/guideline.tex")
    assert tex["exists"] is True
    assert len(tex["sha256"]) == 64
    assert summary["secret_values_included"] is False
    markdown = render_markdown(summary)
    assert "deepseek/test" in markdown
    assert "Total tokens reported: `150`" in markdown


def test_benchmark_summary_distinguishes_source_and_workflow_commits_and_counts_report_errors(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "output").mkdir()
    state = {
        "model_usage": {"provider": "nararouter", "logical_calls": 4, "http_attempts": 6},
        "last_run_status": "error",
    }
    (tmp_path / "state" / "current_state.json").write_text(json.dumps(state), encoding="utf-8")
    report_text = (
        "# FEA Pipeline - Cycle Report\n\n"
        "## Errors\n"
        "- Runtime exception during extract: provider interface failure\n"
        "- Section paragraph validation failed\n"
    )
    (tmp_path / "output" / "validation_report.md").write_text(report_text, encoding="utf-8")
    runtime = {
        "schema_version": 1,
        "status": "error",
        "active_phase": "extract",
        "source_commit": "sourceabc",
        "workflow_commit": "workflowxyz",
        "phase_events": [
            {"phase": "research", "status": "completed", "delta": {"logical_calls": 2, "http_attempts": 2}},
            {"phase": "extract", "status": "failed", "delta": {"logical_calls": 1, "http_attempts": 1}, "error_type": "AttributeError"},
        ],
        "failure": {"phase": "extract", "exception_type": "AttributeError", "message": "missing provider counter"},
    }
    (tmp_path / "output" / "provider_runtime_diagnostics.json").write_text(json.dumps(runtime), encoding="utf-8")

    summary = build_summary(tmp_path, {
        "provider": "nararouter",
        "model": "agnes-2.5-flash",
        "target_branch": "stage1/section-uuids",
        "source_commit": "sourceabc",
        "workflow_commit": "workflowxyz",
        "max_tokens_per_call": 12000,
        "max_llm_calls": 80,
        "pipeline_outcome": "failure",
        "publication_outcome": "not_run",
    })
    benchmark = summary["benchmark"]
    assert benchmark["source_commit"] == "sourceabc"
    assert benchmark["workflow_commit"] == "workflowxyz"
    assert benchmark["commit"] == "sourceabc"
    assert benchmark["errors_recorded"] == 2
    assert summary["provider_runtime_diagnostics"]["active_phase"] == "extract"
    assert [p["phase"] for p in summary["provider_runtime_diagnostics"]["phases"]] == ["research", "extract"]
    markdown = render_markdown(summary)
    assert "Source checkout commit: `sourceabc`" in markdown
    assert "Workflow commit: `workflowxyz`" in markdown
    assert "Runtime phase trace" in markdown

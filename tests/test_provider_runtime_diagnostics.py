import os

from core.provider_runtime_diagnostics import (
    finalize_provider_diagnostics,
    get_provider_call_count,
    provider_snapshot,
    record_provider_phase,
)


class FakeProvider:
    provider_name = "openrouter"
    model = "deepseek/test"

    def __init__(self):
        self.logical_calls = 2
        self.successful_calls = 1
        self.failed_calls = 1
        self.http_attempts = 3
        self.usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}

    def get_stats(self):
        return {
            "provider": self.provider_name,
            "model": self.model,
            "logical_calls": self.logical_calls,
            "total_calls": self.logical_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "http_attempts": self.http_attempts,
            "usage": dict(self.usage),
            "last_errors": [f"authorization failed for {os.environ.get('OPENROUTER_TOKEN', '')}"],
        }


def test_call_count_reads_logical_and_legacy_total_calls():
    class Logical:
        logical_calls = 3

    class Legacy:
        total_calls = 7

    assert get_provider_call_count(Logical()) == 3
    assert get_provider_call_count(Legacy()) == 7


def test_call_count_fails_clearly_when_provider_has_no_counter():
    class Missing:
        pass

    try:
        get_provider_call_count(Missing())
    except TypeError as exc:
        assert "logical_calls or total_calls" in str(exc)
    else:
        raise AssertionError("missing provider counter must not silently become zero")


def test_phase_event_records_deltas_and_redacts_provider_secret(monkeypatch):
    monkeypatch.setenv("OPENROUTER_TOKEN", "test-secret-token")
    provider = FakeProvider()
    before = provider_snapshot(provider)
    provider.logical_calls += 1
    provider.successful_calls += 1
    provider.http_attempts += 1
    provider.usage["prompt_tokens"] += 50
    provider.usage["completion_tokens"] += 10
    provider.usage["total_tokens"] += 60
    state = {"provider_runtime_diagnostics": {"schema_version": 1, "phase_events": []}}

    event = record_provider_phase(state, provider, "extract", "completed", before=before)
    assert event["delta"]["logical_calls"] == 1
    assert event["delta"]["http_attempts"] == 1
    assert event["delta"]["usage"]["total_tokens"] == 60
    assert "test-secret-token" not in repr(event)
    assert state["provider_runtime_diagnostics"]["phase_events"][-1]["phase"] == "extract"


def test_finalize_records_failure_phase_and_both_revisions(monkeypatch):
    monkeypatch.setenv("FEA_SOURCE_COMMIT", "source123")
    monkeypatch.setenv("FEA_WORKFLOW_COMMIT", "workflow456")
    provider = FakeProvider()
    state = {}
    runtime = finalize_provider_diagnostics(
        state, provider, "error", active_phase="extract",
        error=AttributeError("missing total_calls"),
    )
    assert runtime["status"] == "error"
    assert runtime["active_phase"] == "extract"
    assert runtime["source_commit"] == "source123"
    assert runtime["workflow_commit"] == "workflow456"
    assert runtime["failure"]["exception_type"] == "AttributeError"

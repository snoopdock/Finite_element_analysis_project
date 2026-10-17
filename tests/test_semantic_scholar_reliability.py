"""Deterministic tests for anonymous Semantic Scholar throttling behavior."""
from __future__ import annotations

import research.semantic_scholar as semantic_scholar


class FakeResponse:
    def __init__(self, status_code, data=None, headers=None, text=""):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.text = text or str(self._data)

    def json(self):
        return self._data


def _paper(paper_id, title):
    return {
        "paperId": paper_id,
        "title": title,
        "abstract": "A useful abstract about finite element methods.",
        "authors": [{"name": "Example Author"}],
        "year": 2024,
        "citationCount": 1,
        "openAccessPdf": None,
    }


def _reset_pacing(monkeypatch):
    monkeypatch.setattr(semantic_scholar, "_LAST_SEMANTIC_SCHOLAR_REQUEST_AT", 0.0)
    monkeypatch.setattr(semantic_scholar, "_SEMANTIC_SCHOLAR_COOLDOWN_UNTIL", 0.0)
    monkeypatch.setattr(semantic_scholar.time, "sleep", lambda seconds: None)


def test_429_then_success_returns_records_and_records_retry(monkeypatch):
    _reset_pacing(monkeypatch)
    responses = [
        FakeResponse(429, {"message": "Too Many Requests"}, {"Retry-After": "1"}),
        FakeResponse(200, {"data": [_paper("test-paper-a", "Paper A"), _paper("test-paper-b", "Paper B")]}),
    ]
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    monkeypatch.setattr(semantic_scholar, "read_cache", lambda source_id: None)
    records = semantic_scholar.search_semantic_scholar("finite element method", max_results=3)

    assert len(records) == 2
    assert [record["title"] for record in records] == ["Paper A", "Paper B"]
    assert len(calls) == 2
    status = semantic_scholar.get_last_retrieval_status()
    assert status["status"] == "success"
    assert status["attempt_count"] == 2
    assert status["retry_count"] == 1
    assert status["returned_records"] == 2


def test_repeated_429_stops_at_attempt_budget_and_reports_rate_limit(monkeypatch):
    _reset_pacing(monkeypatch)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(429, {"message": "Too Many Requests"})

    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    records = semantic_scholar.search_semantic_scholar("finite element method", max_results=3)

    assert records == []
    assert len(calls) == semantic_scholar.SEMANTIC_SCHOLAR_MAX_ATTEMPTS == 3
    status = semantic_scholar.get_last_retrieval_status()
    assert status["status"] == "rate_limited"
    assert status["http_status"] == 429
    assert status["attempt_count"] == 3
    assert status["retry_count"] == 2


def test_long_retry_after_is_respected_by_not_retrying_early(monkeypatch):
    _reset_pacing(monkeypatch)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(429, {"message": "Too Many Requests"}, {"Retry-After": "120"})

    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    records = semantic_scholar.search_semantic_scholar("finite element method", max_results=1)

    assert records == []
    assert len(calls) == 1
    status = semantic_scholar.get_last_retrieval_status()
    assert status["status"] == "rate_limited"
    assert status["retry_stop_reason"] == "retry_after_exceeds_bounded_wait"
    assert status["retry_count"] == 0

    # The next query in this process must honor the same cooldown without
    # issuing another upstream request.
    deferred = semantic_scholar.search_semantic_scholar("another query", max_results=1)
    assert deferred == []
    assert len(calls) == 1
    deferred_status = semantic_scholar.get_last_retrieval_status()
    assert deferred_status["status"] == "rate_limited"
    assert deferred_status["retry_stop_reason"] == "provider_cooldown_active"
    assert deferred_status["attempt_count"] == 0


def test_non_429_http_error_is_not_retried(monkeypatch):
    _reset_pacing(monkeypatch)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(503, {"message": "temporarily unavailable"})

    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    records = semantic_scholar.search_semantic_scholar("finite element method", max_results=1)

    assert records == []
    assert len(calls) == 1
    status = semantic_scholar.get_last_retrieval_status()
    assert status["status"] == "server_error"
    assert status["http_status"] == 503
    assert status["attempt_count"] == 1
    assert status["retry_count"] == 0


def test_concurrent_search_api_calls_are_serialized(monkeypatch):
    import threading

    _reset_pacing(monkeypatch)
    monkeypatch.setattr(semantic_scholar, "SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0

    class FastResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {"data": []}

    def fake_get(url, **kwargs):
        nonlocal active, maximum_active
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        # Give a competing thread an opportunity to enter the request path.
        threading.Event().wait(0.02)
        with state_lock:
            active -= 1
        return FastResponse()

    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    results = []
    def run_one(query):
        results.append(semantic_scholar._request_search_api({"query": query}, {}, timeout=1))

    threads = [threading.Thread(target=run_one, args=(f"query-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    assert maximum_active == 1


def test_network_error_preserves_prior_http_attempt_telemetry(monkeypatch):
    _reset_pacing(monkeypatch)
    calls = []
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            return FakeResponse(429, {"message": "Too Many Requests"})
        raise semantic_scholar.requests.exceptions.ConnectionError("connection dropped")
    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    records = semantic_scholar.search_semantic_scholar("finite element method", max_results=1)
    assert records == []
    assert len(calls) == 2
    status = semantic_scholar.get_last_retrieval_status()
    assert status["status"] == "network_error"
    assert status["attempt_count"] == 2
    assert status["retry_count"] == 1
    assert status["http_attempt_statuses"] == [429]

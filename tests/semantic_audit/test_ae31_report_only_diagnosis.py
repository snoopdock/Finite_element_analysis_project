from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import textwrap

import pytest

from audit_engine.semantic_audit.ae29.controller import RepositorySnapshot
from audit_engine.semantic_audit.ae31 import diagnosis as ae31


def _valid_model_json() -> str:
    return json.dumps({
        "summary": "The recorded failures are HTTP throttling responses.",
        "root_cause_codes": ["unauthenticated_shared_rate_limit", "concurrent_request_fanout", "missing_retry_after_backoff"],
        "causal_chain": ["Several query tasks can overlap.", "The endpoint returns 429.", "The retriever returns an empty result without retrying."],
        "evidence": [
            {"path": "research/semantic_scholar.py", "start_line": 2, "end_line": 4, "claim_type": "direct_observation", "claim": "The retriever handles HTTP 429."},
            {"path": "state_report", "start_line": None, "end_line": None, "claim_type": "direct_observation", "claim": "The stored report includes a 429."}
        ],
        "alternative_hypotheses": ["Provider-side throttling may vary over time."],
        "proposed_changes": ["Add optional x-api-key support.", "Use bounded Retry-After-aware backoff."],
        "proposed_unified_diff": "",
        "test_plan": ["Mock 429 and Retry-After.", "Test success after a bounded retry."],
        "code_fix_feasible_without_semantic_scholar_key": True,
        "reliable_access_guaranteed_without_semantic_scholar_key": False,
        "risks": ["Retry storms must be prevented."],
        "remaining_questions": ["Does a bounded anonymous probe return a useful number of records?"]
    })


def _fixture_repo(root: Path) -> Path:
    (root / "research").mkdir(parents=True)
    (root / "state").mkdir()
    (root / "providers").mkdir()
    (root / "tests").mkdir()
    (root / "config.yaml").write_text("seed_queries: []\n", encoding="utf-8")
    (root / "research/semantic_scholar.py").write_text(textwrap.dedent("""
        API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
        if response.status_code == 429:
            status = "rate_limited"
            return []
        time.sleep(1)
    """).lstrip(), encoding="utf-8")
    (root / "research/evidence.py").write_text(textwrap.dedent("""
        from concurrent.futures import ThreadPoolExecutor
        def retrieve_evidence_parallel(queries, max_workers=3):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                pass
    """).lstrip(), encoding="utf-8")
    (root / "providers/cloudflare.py").write_text("class CloudflareProvider: pass\n", encoding="utf-8")
    (root / "tests/test_acquisition_adapter.py").write_text("def test_status_mapping():\n    assert True\n", encoding="utf-8")
    (root / "tests/test_evidence_adapter.py").write_text("def test_evidence():\n    assert True\n", encoding="utf-8")
    (root / "tests/test_semantic_scholar_reliability.py").write_text("def test_retry_policy():\n    assert True\n", encoding="utf-8")
    state = {
        "last_run": "2026-10-06T16:04:18Z",
        "last_run_status": "partial",
        "retrieval_report": {
            "status": "partial_failure", "retrieved_at": "2026-10-06T16:03:11Z", "query_count": 2,
            "providers": {"semantic_scholar": {
                "status": "partial_failure", "attempts": [
                    {"status": "rate_limited", "http_status": 429, "query": "query A", "returned_records": 0},
                    {"status": "success", "query": "query B", "returned_records": 2}
                ]
            }}
        },
        "retrieval_history": {"events": []}
    }
    (root / "state/current_state.json").write_text(json.dumps(state), encoding="utf-8")
    return root


def test_ae29_snapshot_digest_matches_real_ae29_snapshot():
    files = {"src/a.py": b"x = 1\n", "tests/test_a.py": b"assert True\n"}
    digest, manifest = ae31.ae29_compatible_snapshot(files)
    assert digest == RepositorySnapshot(files).snapshot_sha256
    assert manifest == list(RepositorySnapshot(files).manifest)


def test_historical_summary_counts_current_429_and_separates_history():
    state = {
        "last_run_status": "partial",
        "retrieval_report": {"status": "partial_failure", "providers": {
            "semantic_scholar": {"status": "rate_limited", "attempts": [
                {"status": "rate_limited", "http_status": 429, "query": "q", "returned_records": 0}
            ]}
        }},
        "retrieval_history": {"events": [{"report": {"status": "rate_limited", "providers": {
            "semantic_scholar": {"status": "rate_limited", "attempts": [
                {"status": "rate_limited", "http_status": 429, "query": "old q", "returned_records": 0}
            ]}
        }}}]}
    }
    summary = ae31.extract_retrieval_summary(json.dumps(state).encode())
    assert summary["current_report"]["semantic_scholar"]["status_counts"]["rate_limited"] == 1
    assert summary["recent_history_events"][0]["semantic_scholar"]["status_counts"]["rate_limited"] == 1
    assert summary["combined_status_counts_current_plus_recent_history"]["rate_limited"] == 2


def test_invalid_state_is_reported_not_raised():
    summary = ae31.extract_retrieval_summary(b"not json")
    assert summary["status"] == "state_parse_error"


def test_safe_read_rejects_path_traversal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(ae31.DiagnosticError):
        ae31.safe_read_file(root, "../outside.txt")


def test_safe_read_rejects_symlink(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "research").mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret source", encoding="utf-8")
    (root / "research/link.py").symlink_to(outside)
    with pytest.raises(ae31.DiagnosticError, match="Symlinked"):
        ae31.safe_read_file(root, "research/link.py")


def test_finding_is_bound_to_scoped_snapshot():
    files = {"research/semantic_scholar.py": b"source\n", "research/evidence.py": b"runner\n", "state/current_state.json": b"{}"}
    snapshot_sha, _ = ae31.ae29_compatible_snapshot(files)
    finding = ae31._make_finding(snapshot_sha, files, {"current_report": {"semantic_scholar": {"status_counts": {"rate_limited": 1}, "attempt_count": 1}}})
    assert finding["schema_version"] == "ae29/repository-audit-finding/v1"
    assert finding["snapshot_sha256"] == snapshot_sha
    expected = ae31.sha256_json({key: finding[key] for key in ("rule_id", "category", "severity", "title", "evidence")})
    assert finding["finding_fingerprint"] == expected


def test_model_response_schema_accepts_expected_contract():
    parsed, status = ae31._parse_json_object(_valid_model_json())
    assert status == "valid"
    assert parsed is not None


def test_model_response_schema_rejects_unknown_root_cause_code():
    payload = json.loads(_valid_model_json())
    payload["root_cause_codes"] = ["made_up_cause"]
    parsed, status = ae31._parse_json_object(json.dumps(payload))
    assert parsed is None
    assert "unsupported" in status


def test_claim_review_flags_unknown_evidence_path_and_protected_diff():
    payload = json.loads(_valid_model_json())
    payload["evidence"] = [{"path": "src/imagined.py", "start_line": 1, "end_line": 2, "claim_type": "direct_observation", "claim": "imagined"}]
    payload["proposed_unified_diff"] = "--- a/.github/workflows/secret.yml\n+++ b/.github/workflows/secret.yml\n@@ -1 +1 @@\n-a\n+b\n"
    review = ae31._validate_model_claims(payload, {"research/semantic_scholar.py": b"one\ntwo\n"})
    assert review["evidence_reference_warnings"]
    assert review["proposed_diff_scope_status"] == "flagged"
    assert any("protected path" in item for item in review["proposed_diff_scope_warnings"])


def test_claim_review_resolves_actual_source_excerpt():
    payload = json.loads(_valid_model_json())
    payload["evidence"] = [{"path": "research/semantic_scholar.py", "start_line": 1, "end_line": 2, "claim_type": "direct_observation", "claim": "source lines"}]
    review = ae31._validate_model_claims(payload, {"research/semantic_scholar.py": b"line one\nline two\n"})
    assert review["resolved_evidence_excerpts"][0]["source_excerpt"] == "1: line one\n2: line two"


def test_cloudflare_response_parsing_and_secret_redaction(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""
        def json(self):
            return {"success": True, "result": {"response": "answer sk-test-secret"}}
    monkeypatch.setattr(ae31.requests, "post", lambda *args, **kwargs: FakeResponse())
    result = ae31.call_cloudflare(
        account_id="account-id", api_token="token", model="@cf/model/test",
        messages=[{"role": "user", "content": "diagnose"}], secrets_to_redact=["sk-test-secret", "token"]
    )
    assert result["status"] == "success"
    assert "sk-test-secret" not in result["raw_output"]
    assert result["raw_output"] == "answer [REDACTED]"
    assert result["raw_output_sha256"] == hashlib.sha256(result["raw_output"].encode()).hexdigest()


@pytest.mark.parametrize("model", ae31.NARAROUTER_MODELS)
def test_nararouter_uses_explicit_model_without_discovery(monkeypatch, model):
    class FakeResponse:
        status_code = 200
        text = ""
        def json(self):
            return {"model": model, "choices": [{"message": {"content": "diagnosis"}}]}

    def forbidden_get(*args, **kwargs):
        pytest.fail("NaraRouter model discovery must not be called")

    post_calls = []
    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(ae31.requests, "get", forbidden_get)
    monkeypatch.setattr(ae31.requests, "post", fake_post)
    result = ae31.call_nararouter(
        api_key="secret", model=model,
        messages=[{"role": "user", "content": "x"}],
        secrets_to_redact=["secret"],
    )
    assert result["status"] == "success"
    assert result["model"] == model
    assert result["model_selection"] == "explicit configured model"
    assert post_calls[0][0] == "https://router.bynara.id/v1/chat/completions"
    assert post_calls[0][1]["headers"]["Authorization"] == "Bearer secret"
    assert post_calls[0][1]["json"]["model"] == model
    assert result["raw_output"] == "diagnosis"


def test_nararouter_auto_or_unknown_model_is_rejected_without_network(monkeypatch):
    monkeypatch.setattr(ae31.requests, "get", lambda *a, **k: pytest.fail("no discovery"))
    monkeypatch.setattr(ae31.requests, "post", lambda *a, **k: pytest.fail("no chat call"))
    result = ae31.call_nararouter(api_key="secret", model="auto", messages=[])
    assert result["status"] == "configuration_error"
    assert "explicit NaraRouter model" in result["error"]


def test_nararouter_normalizes_accidental_bearer_prefix(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}
    calls = []
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()
    monkeypatch.setattr(ae31.requests, "post", fake_post)
    result = ae31.call_nararouter(
        api_key="Bearer secret-token", model="agnes-2.5-flash", messages=[],
        secrets_to_redact=["Bearer secret-token"],
    )
    assert result["status"] == "success"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret-token"


def test_nararouter_401_is_actionable_and_does_not_expose_key(monkeypatch):
    class FakeResponse:
        status_code = 401
        text = '{"error":"A valid API key is required."}'
    monkeypatch.setattr(ae31.requests, "post", lambda *a, **k: FakeResponse())
    result = ae31.call_nararouter(
        api_key="secret-nara-key", model="agnes-2.5-flash", messages=[],
        secrets_to_redact=["secret-nara-key"],
    )
    assert result["status"] == "provider_error"
    assert result["http_status"] == 401
    assert "NARAROUTER_API_KEY" in result["error"]
    assert "secret-nara-key" not in result["error"]



@pytest.mark.parametrize("model", ae31.OPENROUTER_MODELS)
def test_openrouter_uses_explicit_allowlisted_model_without_discovery(monkeypatch, model):
    class FakeResponse:
        status_code = 200
        text = ""
        def json(self):
            return {
                "model": model,
                "choices": [{"message": {"content": _valid_model_json()}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
            }

    calls = []
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(ae31.requests, "get", lambda *a, **k: pytest.fail("OpenRouter model discovery is not used"))
    monkeypatch.setattr(ae31.requests, "post", fake_post)
    result = ae31.call_openrouter(
        api_token="openrouter-test-secret", model=model,
        messages=[{"role": "user", "content": "diagnose"}],
        secrets_to_redact=["openrouter-test-secret"],
    )
    assert result["status"] == "success"
    assert result["provider"] == "openrouter"
    assert result["model"] == model
    assert result["returned_model"] == model
    assert result["raw_output"] == _valid_model_json()
    assert result["raw_output_sha256"] == hashlib.sha256(_valid_model_json().encode()).hexdigest()
    assert result["usage"]["total_tokens"] == 46
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer openrouter-test-secret"
    assert kwargs["headers"]["HTTP-Referer"].startswith("https://github.com/")
    assert kwargs["json"]["model"] == model
    assert kwargs["json"]["stream"] is False


def test_openrouter_unknown_model_is_rejected_without_network(monkeypatch):
    monkeypatch.setattr(ae31.requests, "post", lambda *a, **k: pytest.fail("No request for unapproved model"))
    result = ae31.call_openrouter(api_token="secret", model="provider/unknown", messages=[])
    assert result["status"] == "configuration_error"
    assert "no request was sent" in result["error"]


def test_openrouter_401_is_actionable_and_does_not_expose_key(monkeypatch):
    class FakeResponse:
        status_code = 401
        text = '{"error":"invalid key secret-openrouter-key"}'
    monkeypatch.setattr(ae31.requests, "post", lambda *a, **k: FakeResponse())
    result = ae31.call_openrouter(
        api_token="secret-openrouter-key", model=ae31.OPENROUTER_MODELS[0], messages=[],
        secrets_to_redact=["secret-openrouter-key"],
    )
    assert result["status"] == "provider_error"
    assert result["http_status"] == 401
    assert "OPENROUTER_TOKEN" in result["error"]
    assert "secret-openrouter-key" not in result["error"]


def test_openrouter_missing_secret_is_skipped_without_network(monkeypatch):
    monkeypatch.setattr(ae31.requests, "post", lambda *a, **k: pytest.fail("No request without token"))
    for model in ae31.OPENROUTER_MODELS:
        result = ae31.call_openrouter(api_token="", model=model, messages=[])
        assert result["status"] == "skipped"
        assert result["provider"] == "openrouter"


def test_openrouter_bearer_prefix_is_normalized_and_redacted(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""
        def json(self):
            return {"model": ae31.OPENROUTER_MODELS[0], "choices": [{"message": {"content": "ok"}}]}
    calls = []
    monkeypatch.setattr(ae31.requests, "post", lambda url, **kwargs: (calls.append((url, kwargs)) or FakeResponse()))
    result = ae31.call_openrouter(
        api_token="Bearer openrouter-secret", model=ae31.OPENROUTER_MODELS[0], messages=[],
        secrets_to_redact=["Bearer openrouter-secret"],
    )
    assert result["status"] == "success"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer openrouter-secret"
    assert "openrouter-secret" not in result["raw_output"]


def test_live_probe_retries_429_then_returns_records(monkeypatch):
    calls = []
    class FakeResponse:
        def __init__(self, status_code, data, headers=None):
            self.status_code = status_code
            self._data = data
            self.headers = headers or {}
            self.text = json.dumps(data)
        def json(self):
            return self._data
    responses = [
        FakeResponse(429, {"message": "Too Many Requests"}, {"Retry-After": "1"}),
        FakeResponse(200, {"data": [{"title": "Paper A"}, {"title": "Paper B"}]}, {}),
    ]
    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return responses.pop(0)
    monkeypatch.setattr(ae31.requests, "get", fake_get)
    monkeypatch.setattr(ae31.time, "sleep", lambda seconds: None)
    result = ae31.probe_semantic_scholar()
    assert result["status"] == "success"
    assert result["result_count"] == 2
    assert result["attempt_count"] == 2
    assert result["retry_count"] == 1
    assert result["yield_assessment"] == "few_records_returned"
    assert [row["http_status"] for row in result["attempts"]] == [429, 200]
    assert len(calls) == 2
    assert calls[0][1]["params"]["limit"] == 3


def test_live_probe_stops_after_bounded_429_attempts(monkeypatch):
    calls = []
    class FakeResponse:
        status_code = 429
        headers = {}
        text = '{"message":"Too Many Requests"}'
        def json(self):
            return {"message": "Too Many Requests"}
    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()
    monkeypatch.setattr(ae31.requests, "get", fake_get)
    monkeypatch.setattr(ae31.time, "sleep", lambda seconds: None)
    result = ae31.probe_semantic_scholar()
    assert result["status"] == "rate_limited"
    assert result["http_status"] == 429
    assert result["attempt_count"] == ae31.S2_PROBE_MAX_ATTEMPTS == 3
    assert result["retry_count"] == 2
    assert result["retry_stop_reason"] == "max_attempts_reached"
    assert len(calls) == 3


def test_prompt_context_numbers_source_lines_accurately(tmp_path):
    repo = _fixture_repo(tmp_path / "repo")
    files, _, _ = ae31.read_scoped_snapshot(repo)
    snapshot_sha, manifest = ae31.ae29_compatible_snapshot(files)
    history = ae31.extract_retrieval_summary(files["state/current_state.json"])
    finding = ae31._make_finding(snapshot_sha, files, history)
    audit = ae31._make_audit_report(snapshot_sha, finding, "a" * 64)
    context = ae31._build_prompt_context(files, snapshot_sha, manifest, finding, audit, {"status": "not_run"})
    source = context["repository_code_and_tests_with_actual_line_numbers"]["research/semantic_scholar.py"]
    assert source.startswith("0001: API_URL")
    assert "Manifest size values are byte counts, not line counts" in context["source_line_numbering_note"]


def test_prompt_context_is_bounded_and_preserves_original_line_numbers(tmp_path):
    repo = _fixture_repo(tmp_path / "repo")
    # Simulate a large source file that previously pushed the full prompt over budget.
    lines = [f"# unrelated filler line {index}" for index in range(1, 2200)]
    lines[1199] = "def search_semantic_scholar(query):"
    lines[1200] = '    response = requests.get(API_URL, params={"query": query})'
    lines[1201] = "    if response.status_code == 429:"
    lines[1202] = "        time.sleep(2)  # Retry-After bounded backoff"
    (repo / "research/semantic_scholar.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files, _, _ = ae31.read_scoped_snapshot(repo)
    snapshot_sha, manifest = ae31.ae29_compatible_snapshot(files)
    history = ae31.extract_retrieval_summary(files["state/current_state.json"])
    finding = ae31._make_finding(snapshot_sha, files, history)
    audit = ae31._make_audit_report(snapshot_sha, finding, "a" * 64)
    context = ae31._build_prompt_context(files, snapshot_sha, manifest, finding, audit, {"status": "not_run"})
    source = context["repository_code_and_tests_with_actual_line_numbers"]["research/semantic_scholar.py"]
    excerpt = context["evidence_excerpt_manifest"]["research/semantic_scholar.py"]
    assert len(source) <= ae31.MAX_SOURCE_EXCERPT_CHARS["research/semantic_scholar.py"]
    assert "... omitted original lines" in source
    assert '1201:     response = requests.get' in source
    assert excerpt["omitted_lines"] > 0
    assert any(start <= 1200 <= end for start, end in excerpt["visible_line_ranges"])
    _, prompt = ae31._build_prompt(
        request_envelope={"request_sha256": "a" * 64}, prompt_context=context
    )
    assert len(prompt) <= ae31.MAX_PROMPT_CHARS


def test_oversized_single_source_line_is_marked_and_not_trusted_as_full_evidence():
    source, visible_ranges, stats = ae31._numbered_excerpt(
        "research/semantic_scholar.py", ("x" * 5000 + "\nnormal line\n").encode(), 2500
    )
    assert len(source) <= 2500
    assert "LINE CONTENT TRUNCATED" in source
    assert stats["truncated_lines_shown"] == [1]
    payload = json.loads(_valid_model_json())
    payload["evidence"] = [{
        "path": "research/semantic_scholar.py", "start_line": 1, "end_line": 1,
        "claim_type": "direct_observation", "claim": "claim based on the line",
    }]
    review = ae31._validate_model_claims(
        payload,
        {"research/semantic_scholar.py": ("x" * 5000 + "\nnormal line\n").encode()},
        {"research/semantic_scholar.py": visible_ranges},
        {"research/semantic_scholar.py": stats["truncated_lines_shown"]},
    )
    assert any("truncated source content" in warning for warning in review["evidence_reference_warnings"])


def test_prompt_size_error_includes_diagnostic_metrics(monkeypatch):
    monkeypatch.setattr(ae31, "MAX_PROMPT_CHARS", 100)
    with pytest.raises(ae31.DiagnosticError, match="prompt exceeds") as caught:
        ae31._build_prompt(
            request_envelope={"request_sha256": "a" * 64},
            prompt_context={"source": "x" * 500},
        )
    assert caught.value.details["phase"] == "prompt_construction"
    assert caught.value.details["prompt_chars"] > caught.value.details["prompt_limit_chars"]
    assert caught.value.details["prompt_context_json_chars"] > 0


def test_prompt_failure_retains_live_probe_and_snapshot_manifest(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    probe = {
        "status": "rate_limited", "http_status": 429, "attempt_count": 3,
        "retry_count": 2, "attempts": [
            {"attempt": 1, "http_status": 429},
            {"attempt": 2, "http_status": 429},
            {"attempt": 3, "http_status": 429},
        ],
    }
    monkeypatch.setattr(ae31, "probe_semantic_scholar", lambda: probe)
    monkeypatch.setattr(
        ae31, "_build_prompt",
        lambda **kwargs: (_ for _ in ()).throw(ae31.DiagnosticError(
            "LLM prompt exceeds 120000 character limit",
            details={"prompt_chars": 130001, "prompt_limit_chars": 120000},
        )),
    )
    with pytest.raises(ae31.DiagnosticError, match="prompt exceeds") as caught:
        ae31.run_diagnostic(repo_root=repo, output_path=tmp_path / "report.txt", environment={})
    details = caught.value.details
    assert details["phase"] == "prompt_construction"
    assert details["live_semantic_scholar_probe"] == probe
    assert details["snapshot_sha256"]
    assert any(row["path"] == "research/semantic_scholar.py" for row in details["manifest"])
    assert details["prompt_chars"] == 130001


def test_runner_error_writes_probe_context_and_returns_nonzero(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    output = tmp_path / "failure.txt"
    details = {
        "phase": "prompt_construction",
        "live_semantic_scholar_probe": {"status": "rate_limited", "http_status": 429, "attempt_count": 3},
        "prompt_chars": 130001,
        "prompt_limit_chars": 120000,
        "manifest": [{"path": "research/semantic_scholar.py", "sha256": "a" * 64, "size": 100}],
    }
    monkeypatch.setattr(ae31, "run_diagnostic", lambda **kwargs: (_ for _ in ()).throw(
        ae31.DiagnosticError("LLM prompt exceeds 120000 character limit", details=details)
    ))
    result = ae31.main([
        "--repo-root", str(repo), "--output", str(output),
        "--target-branch", "stage1/section-uuids", "--target-commit", "abc123",
    ])
    report = output.read_text(encoding="utf-8")
    assert result == 1
    assert "Status: runner_error" in report
    assert "Failure phase: prompt_construction" in report
    assert '"http_status": 429' in report
    assert '"prompt_chars": 130001' in report
    assert "Target repository files modified: NO" in report


def test_semantic_scholar_recommendation_uses_two_record_minimum():
    keep = ae31._semantic_scholar_operational_recommendation({
        "status": "success", "result_count": 2, "attempt_count": 2,
    })
    remove_empty = ae31._semantic_scholar_operational_recommendation({
        "status": "success", "result_count": 1, "attempt_count": 3,
    })
    remove_throttled = ae31._semantic_scholar_operational_recommendation({
        "status": "rate_limited", "http_status": 429, "attempt_count": 3,
    })
    inconclusive = ae31._semantic_scholar_operational_recommendation({
        "status": "network_error", "attempt_count": 1,
    })
    assert keep["decision"] == "keep_under_rate_limit_controls"
    assert remove_empty["decision"] == "recommend_removal_from_active_pipeline"
    assert remove_throttled["decision"] == "recommend_removal_from_active_pipeline"
    assert inconclusive["decision"] == "inconclusive_no_provider_change"


def test_report_only_workflow_writes_report_without_modifying_target(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    out = tmp_path / "report.txt"
    (repo / "research/semantic_scholar.py").write_text(
        (repo / "research/semantic_scholar.py").read_text(encoding="utf-8") + "\n# Authorization: Bearer cfsecret\n",
        encoding="utf-8",
    )
    before = {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.rglob("*") if p.is_file()}
    payload = _valid_model_json()
    captured_messages = []
    def fake_provider(**kwargs):
        captured_messages.append(kwargs["messages"])
        return {"status": "success", "provider": "mock", "model": "fixture", "http_status": 200,
                "elapsed_ms": 1, "raw_output": payload, "raw_output_sha256": hashlib.sha256(payload.encode()).hexdigest()}
    monkeypatch.setattr(ae31, "call_cloudflare", fake_provider)
    monkeypatch.setattr(ae31, "call_nararouter", fake_provider)
    def fake_openrouter(**kwargs):
        captured_messages.append(kwargs["messages"])
        model = kwargs["model"]
        raw = payload
        return {"status": "success", "provider": "openrouter", "model": model,
                "returned_model": model, "http_status": 200, "elapsed_ms": 1,
                "raw_output": raw, "raw_output_sha256": hashlib.sha256(raw.encode()).hexdigest()}
    monkeypatch.setattr(ae31, "call_openrouter", fake_openrouter)
    monkeypatch.setattr(ae31, "probe_semantic_scholar", lambda: {"status": "success", "http_status": 200, "result_count": 1})
    result = ae31.run_diagnostic(
        repo_root=repo, output_path=out, target_branch="stage1/section-uuids", target_commit="abc123",
        environment={"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "cfsecret",
                     "NARAROUTER_API_KEY": "narasecret", "OPENROUTER_TOKEN": "orsecret"},
    )
    after = {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.rglob("*") if p.is_file()}
    assert out.exists()
    assert "REPORT_ONLY" in out.read_text(encoding="utf-8")
    assert "Automatic self-correction: DISABLED" in out.read_text(encoding="utf-8")
    assert before == after
    assert len(result["snapshot_sha256"]) == 64
    assert result["output_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert result["cross_provider_comparison"]["status"] == "compared"
    assert result["overall_status"] == "completed_with_schema_valid_llm_response"
    assert "cfsecret" not in out.read_text(encoding="utf-8")
    assert "narasecret" not in out.read_text(encoding="utf-8")
    assert "orsecret" not in out.read_text(encoding="utf-8")
    assert "cfsecret" not in json.dumps(captured_messages)
    assert "orsecret" not in json.dumps(captured_messages)
    assert "[REDACTED]" in json.dumps(captured_messages)
    for model in ae31.OPENROUTER_MODELS:
        assert f"PROVIDER_RESULT\\topenrouter\\t{model}\\tsuccess\\ttrue\\t200" in out.read_text(encoding="utf-8")


def test_output_inside_target_repository_is_rejected_before_calls(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(ae31, "call_cloudflare", lambda **kwargs: pytest.fail("LLM must not be called"))
    with pytest.raises(ae31.DiagnosticError, match="outside the target repository"):
        ae31.run_diagnostic(repo_root=repo, output_path=repo / "report.txt", perform_live_probe=False)


def test_missing_provider_secrets_are_reported_without_network():
    cf = ae31.call_cloudflare(account_id="", api_token="", model="model", messages=[])
    nara = ae31.call_nararouter(api_key="", model="auto", messages=[])
    openrouter = [ae31.call_openrouter(api_token="", model=model, messages=[]) for model in ae31.OPENROUTER_MODELS]
    assert cf["status"] == "skipped"
    assert nara["status"] == "skipped"
    assert all(result["status"] == "skipped" for result in openrouter)


def test_runner_has_no_dynamic_code_execution_or_subprocess_import():
    source = Path(ae31.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert "subprocess" not in imported
    assert "os.system" not in source
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"} for node in ast.walk(tree))


def test_missing_required_evidence_skips_live_calls_and_still_writes_report(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    (repo / "state/current_state.json").unlink()
    monkeypatch.setattr(ae31, "probe_semantic_scholar", lambda: pytest.fail("probe must be skipped"))
    monkeypatch.setattr(ae31, "call_cloudflare", lambda **kwargs: pytest.fail("LLM must be skipped"))
    monkeypatch.setattr(ae31, "call_nararouter", lambda **kwargs: pytest.fail("LLM must be skipped"))
    monkeypatch.setattr(ae31, "call_openrouter", lambda **kwargs: pytest.fail("LLM must be skipped"))
    output = tmp_path / "report.txt"
    result = ae31.run_diagnostic(repo_root=repo, output_path=output, perform_live_probe=True, environment={})
    assert result["overall_status"] == "insufficient_required_evidence"
    assert "state/current_state.json" in result["missing_paths"]
    assert output.exists()
    assert "no model call made" in output.read_text(encoding="utf-8")


def test_cloudflare_http_error_redacts_token(monkeypatch):
    class FakeResponse:
        status_code = 401
        text = "unauthorized token-secret-123456"
    monkeypatch.setattr(ae31.requests, "post", lambda *args, **kwargs: FakeResponse())
    result = ae31.call_cloudflare(
        account_id="acct", api_token="token-secret-123456", model="model",
        messages=[], secrets_to_redact=["token-secret-123456"],
    )
    assert result["status"] == "provider_error"
    assert "token-secret-123456" not in result["error"]
    assert "[REDACTED]" in result["error"]


def test_snapshot_changes_when_any_evidence_byte_changes():
    first, _ = ae31.ae29_compatible_snapshot({"research/semantic_scholar.py": b"return []\n"})
    second, _ = ae31.ae29_compatible_snapshot({"research/semantic_scholar.py": b"return None\n"})
    assert first != second


def test_provider_failures_still_produce_reviewable_report(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(ae31, "probe_semantic_scholar", lambda: {"status": "rate_limited", "http_status": 429, "retry_after": "2"})
    monkeypatch.setattr(ae31, "call_cloudflare", lambda **kwargs: {"status": "provider_error", "provider": "cloudflare", "http_status": 401, "error": "unauthorized"})
    monkeypatch.setattr(ae31, "call_nararouter", lambda **kwargs: {"status": "provider_error", "provider": "nararouter", "http_status": 429, "error": "rate_limited"})
    output = tmp_path / "report.txt"
    result = ae31.run_diagnostic(repo_root=repo, output_path=output, environment={})
    content = output.read_text(encoding="utf-8")
    assert result["overall_status"] == "completed_without_successful_llm_response"
    assert "cloudflare: provider_error" in content
    assert "nararouter: provider_error" in content
    assert "Live Semantic Scholar probe: rate_limited" in content
    assert "Target repository files modified: NO" in content


def test_invalid_json_model_output_is_preserved_but_not_accepted():
    result = {"status": "success", "provider": "mock", "model": "fixture", "raw_output": "I think retrying may help."}
    assessment = ae31._provider_assessment(result, {"research/semantic_scholar.py": b"source\n"})
    assert assessment["schema_valid"] is False
    assert assessment["parse_status"].startswith("invalid_json")
    assert "normalized_diagnosis" not in assessment


def test_nonstandard_diff_without_file_headers_is_flagged():
    payload = json.loads(_valid_model_json())
    payload["proposed_unified_diff"] = "this looks like a change but has no standard file headers"
    review = ae31._validate_model_claims(payload, {"research/semantic_scholar.py": b"source\n"})
    assert review["proposed_diff_scope_status"] == "flagged"
    assert any("could not identify" in item for item in review["proposed_diff_scope_warnings"])


def test_g935_profile_declares_required_identity():
    """The registry schema requires the profile id even when its file exists."""
    repository_root = Path(__file__).resolve().parents[2]
    profile_path = repository_root / "validation" / "profiles" / "G9.35.yaml"
    assert profile_path.is_file(), "G9.35 profile must exist in the repository"
    lines = profile_path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "id: G9.35"


def test_g936_profile_declares_required_identity():
    repository_root = Path(__file__).resolve().parents[2]
    profile_path = repository_root / "validation" / "profiles" / "G9.36.yaml"
    assert profile_path.is_file(), "G9.36 profile must exist in the repository"
    lines = profile_path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "id: G9.36"

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
        "remaining_questions": ["Is an API key available to the owner?"]
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


def test_nararouter_auto_model_discovery_and_chat(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, data, text=""):
            self.status_code = status_code
            self._data = data
            self.text = text
        def json(self):
            return self._data
    get_calls = []
    def fake_get(url, **kwargs):
        get_calls.append(url)
        return FakeResponse(200, {"data": [{"id": "z-model"}, {"id": "deepseek-3.2"}]})
    post_calls = []
    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return FakeResponse(200, {"model": "deepseek-3.2", "choices": [{"message": {"content": "diagnosis"}}]})
    monkeypatch.setattr(ae31.requests, "get", fake_get)
    monkeypatch.setattr(ae31.requests, "post", fake_post)
    result = ae31.call_nararouter(api_key="secret", model="auto", messages=[{"role": "user", "content": "x"}], secrets_to_redact=["secret"])
    assert result["status"] == "success"
    assert result["model"] == "deepseek-3.2"
    assert get_calls == ["https://router.bynara.id/v1/models"]
    assert post_calls[0][0] == "https://router.bynara.id/v1/chat/completions"
    assert result["raw_output"] == "diagnosis"


def test_live_probe_is_one_low_volume_request(monkeypatch):
    calls = []
    class FakeResponse:
        status_code = 429
        headers = {"Retry-After": "2", "x-ratelimit-remaining": "0"}
        text = '{"error":"rate limited"}'
        def json(self):
            return {"error": "rate limited"}
    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()
    monkeypatch.setattr(ae31.requests, "get", fake_get)
    result = ae31.probe_semantic_scholar()
    assert result["status"] == "rate_limited"
    assert result["http_status"] == 429
    assert result["retry_after"] == "2"
    assert len(calls) == 1
    assert calls[0][1]["timeout"] == ae31.S2_PROBE_TIMEOUT_SECONDS


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
    monkeypatch.setattr(ae31, "probe_semantic_scholar", lambda: {"status": "success", "http_status": 200, "result_count": 1})
    result = ae31.run_diagnostic(
        repo_root=repo, output_path=out, target_branch="stage1/section-uuids", target_commit="abc123",
        environment={"CLOUDFLARE_ACCOUNT_ID": "acct", "CLOUDFLARE_API_TOKEN": "cfsecret", "NARAROUTER_API_KEY": "narasecret"},
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
    assert "cfsecret" not in json.dumps(captured_messages)
    assert "[REDACTED]" in json.dumps(captured_messages)


def test_output_inside_target_repository_is_rejected_before_calls(tmp_path, monkeypatch):
    repo = _fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(ae31, "call_cloudflare", lambda **kwargs: pytest.fail("LLM must not be called"))
    with pytest.raises(ae31.DiagnosticError, match="outside the target repository"):
        ae31.run_diagnostic(repo_root=repo, output_path=repo / "report.txt", perform_live_probe=False)


def test_missing_provider_secrets_are_reported_without_network():
    cf = ae31.call_cloudflare(account_id="", api_token="", model="model", messages=[])
    nara = ae31.call_nararouter(api_key="", model="auto", messages=[])
    assert cf["status"] == "skipped"
    assert nara["status"] == "skipped"


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

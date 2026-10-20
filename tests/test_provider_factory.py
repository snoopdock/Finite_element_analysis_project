import pytest

from providers.factory import apply_runtime_overrides, build_provider
from providers.cloudflare import CloudflareProvider
from providers.openai_compatible import OpenAICompatibleProvider


def test_provider_selection_applies_large_benchmark_budgets_and_model():
    config = {"budget": {"max_llm_calls_per_run": 20, "max_tokens_per_call": 2500}, "cloudflare_models": ["old-model"]}
    env = {
        "FEA_LLM_PROVIDER": "openrouter",
        "FEA_LLM_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "FEA_BENCHMARK_MODE": "1",
        "FEA_MAX_LLM_CALLS": "80",
        "FEA_MAX_TOKENS_PER_CALL": "8000",
    }
    provider_name, model = apply_runtime_overrides(config, env)
    assert provider_name == "openrouter"
    assert model == "deepseek/deepseek-v4.1-flash-1017"
    assert config["cloudflare_models"] == [model]
    assert config["budget"] == {"max_llm_calls_per_run": 80, "max_tokens_per_call": 8000}
    assert env["FEA_MAX_LLM_CALLS"] == "80"


def test_benchmark_budget_bounds_reject_excessive_values():
    config = {"budget": {"max_llm_calls_per_run": 20, "max_tokens_per_call": 2500}}
    env = {"FEA_LLM_PROVIDER": "cloudflare", "FEA_BENCHMARK_MODE": "1", "FEA_MAX_LLM_CALLS": "101"}
    with pytest.raises(ValueError, match="between 1 and 100"):
        apply_runtime_overrides(config, env)


def test_openrouter_factory_requires_only_openrouter_secret():
    config = {"budget": {"max_llm_calls_per_run": 10, "max_tokens_per_call": 4000}}
    provider = build_provider(
        config,
        config["budget"],
        "openrouter",
        "deepseek/deepseek-v4.1-flash-1017",
        {"OPENROUTER_TOKEN": "openrouter-only"},
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.provider_name == "openrouter"


def test_nararouter_factory_uses_user_model_and_key():
    config = {"budget": {"max_llm_calls_per_run": 10, "max_tokens_per_call": 4000}}
    provider = build_provider(
        config,
        config["budget"],
        "nararouter",
        "agnes-2.5-flash",
        {"NARAROUTER_API_KEY": "nara-only"},
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "agnes-2.5-flash"


def test_cloudflare_factory_requires_only_cloudflare_credentials():
    config = {"budget": {"max_llm_calls_per_run": 10, "max_tokens_per_call": 4000}, "cloudflare_models": ["cf-model"]}
    provider = build_provider(
        config,
        config["budget"],
        "cloudflare",
        "cf-model",
        {"CLOUDFLARE_ACCOUNT_ID": "account", "CLOUDFLARE_API_TOKEN": "token"},
    )
    assert isinstance(provider, CloudflareProvider)
    assert provider.models == ["cf-model"]


def test_selected_provider_missing_secret_fails_clearly():
    config = {"budget": {"max_llm_calls_per_run": 10, "max_tokens_per_call": 4000}}
    with pytest.raises(RuntimeError, match="OPENROUTER_TOKEN"):
        build_provider(config, config["budget"], "openrouter", "model", {})


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="FEA_LLM_PROVIDER"):
        apply_runtime_overrides({}, {"FEA_LLM_PROVIDER": "unknown"})


def test_cloudflare_honors_benchmark_token_cap(monkeypatch):
    from providers.cloudflare import CloudflareProvider

    seen = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"success": True, "result": {"response": "hello"}}

    def fake_post(url, **kwargs):
        seen.append(kwargs["json"]["max_tokens"])
        return Response()

    monkeypatch.setenv("FEA_BENCHMARK_MODE", "1")
    monkeypatch.setenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", "1")
    monkeypatch.setenv("FEA_MAX_TOKENS_PER_CALL", "8000")
    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    provider = CloudflareProvider("account", "token", ["cf-model"], 2500, max_logical_calls=2)
    text, error = provider.chat([{"role": "user", "content": "hello"}], max_tokens=500)
    assert error is None
    assert text == "hello"
    assert seen == [8000]


def test_cloudflare_structured_chat_requests_api_json_mode(monkeypatch):
    seen = []
    expected = '{"action":"tool_call","tool":"repository_summary","arguments":{},"reason":"Inspect repository."}'

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"success": True, "result": {"response": expected}}

    def fake_post(url, **kwargs):
        seen.append(kwargs["json"])
        return Response()

    monkeypatch.delenv("FEA_BENCHMARK_MODE", raising=False)
    monkeypatch.delenv("FEA_BENCHMARK_FORCE_MAX_TOKENS", raising=False)
    monkeypatch.setattr("providers.cloudflare.requests.post", fake_post)
    provider = CloudflareProvider("account", "token", ["@cf/meta/llama-3.1-8b-instruct-fast"], 2500, max_logical_calls=2)

    text, error = provider.chat_structured([{"role": "user", "content": "Return an action."}], max_tokens=512)

    assert error is None
    assert text == expected
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert provider.get_stats()["structured_json_calls"] == 1

from providers.capabilities import get_provider_capabilities


class UnknownProvider:
    provider_name = "unknown-adapter"
    model = "unknown-model"

    def chat(self, messages, **kwargs):
        return "{}", None


class DeclaredProvider(UnknownProvider):
    def get_capabilities(self):
        return {
            "json_object_mode": True,
            "json_schema_mode": False,
            "native_tool_calls": False,
            "finish_reason_reporting": True,
            "unexpected_capability": True,
        }


def test_unknown_adapter_capabilities_fail_closed():
    result = get_provider_capabilities(UnknownProvider())
    assert result["scope"] == "adapter_declared_not_model_behavior_verified"
    assert result["capabilities"] == {
        "json_object_mode": False,
        "json_schema_mode": False,
        "native_tool_calls": False,
        "finish_reason_reporting": False,
    }


def test_only_explicit_boolean_capabilities_are_accepted():
    result = get_provider_capabilities(
        DeclaredProvider(), provider_name="declared", model_name="model-x"
    )
    assert result["provider"] == "declared"
    assert result["model"] == "model-x"
    assert result["capabilities"]["json_object_mode"] is True
    assert result["capabilities"]["finish_reason_reporting"] is True
    assert result["capabilities"]["json_schema_mode"] is False
    assert "unexpected_capability" not in result["capabilities"]

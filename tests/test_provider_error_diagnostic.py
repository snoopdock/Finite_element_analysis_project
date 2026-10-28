"""Regression tests for safe, actionable provider HTTP-error diagnostics."""
from providers.openai_compatible import http_error_diagnostic
from tools.ae32c_provider_compatibility_smoke import _safe_diagnostics


def test_http_error_diagnostic_classifies_model_rejection_without_storing_message():
    message = "The model agnes-2.5-flash is not available for this account."
    diagnostic = http_error_diagnostic(
        {"error": {"type": "bad_request", "message": message, "request_id": "nr_req_123-abc"}},
        400,
    )
    assert diagnostic["error_message_category"] == "model_identifier_rejected"
    assert diagnostic["error_request_id"] == "nr_req_123-abc"
    assert "message" in diagnostic["error_fields"]
    assert message not in repr(diagnostic)
    assert "agnes-2.5-flash" not in repr(diagnostic)


def test_http_error_diagnostic_classifies_parameter_rejection():
    diagnostic = http_error_diagnostic(
        {"error": {"type": "bad_request", "message": "Unsupported parameter: max_tokens"}},
        400,
    )
    assert diagnostic["error_message_category"] == "request_parameter_rejected"
    assert "max_tokens" not in repr(diagnostic)


def test_http_error_diagnostic_omits_untrusted_request_id():
    diagnostic = http_error_diagnostic(
        {"error": {"message": "Some unknown provider failure", "request_id": "id with spaces and sensitive text"}},
        400,
    )
    assert diagnostic["error_message_category"] == "other_unclassified"
    assert "error_request_id" not in diagnostic
    assert "sensitive text" not in repr(diagnostic)


def test_smoke_safe_diagnostics_preserves_only_category_and_validated_request_id():
    diagnostic = http_error_diagnostic(
        {"error": {"type": "bad_request", "message": "The model is not found", "request_id": "req-7f2"}},
        400,
    )
    output = _safe_diagnostics({"last_http_error_diagnostic": diagnostic})
    safe = output["last_http_error_diagnostic"]
    assert safe["error_message_category"] == "model_identifier_rejected"
    assert safe["error_request_id"] == "req-7f2"
    assert "message" not in safe
    assert "model is not found" not in repr(output)

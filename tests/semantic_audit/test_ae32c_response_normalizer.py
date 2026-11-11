from __future__ import annotations

import pytest

from audit_engine.semantic_audit.ae32c.response_normalizer import (
    ResponseNormalizationError,
    normalize_response,
)


def test_strict_json_is_accepted_unchanged():
    raw = '{"action":"tool_call","tool":"search_repository","arguments":{"query":"x"},"reason":"inspect"}'
    result = normalize_response(raw)
    assert result.strategy == "strict_json"
    assert result.payload["tool"] == "search_repository"


def test_single_markdown_json_fence_is_normalized():
    raw = 'Here is the action:\n```json\n{"action":"final","diagnosis":{"summary":"bounded"}}\n```\n'
    result = normalize_response(raw)
    assert result.strategy == "fenced_json"
    assert result.payload["action"] == "final"


def test_single_embedded_json_object_is_normalized():
    raw = 'I inspected the relevant area. Proposed action: {"action":"tool_call","tool":"search_repository","arguments":{"query":"x"},"reason":"inspect"} End.'
    result = normalize_response(raw)
    assert result.strategy == "embedded_json"
    assert result.payload["action"] == "tool_call"


def test_ambiguous_multiple_json_objects_are_rejected():
    raw = 'First {"action":"final"} then {"action":"tool_call"}.'
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response(raw)
    assert exc.value.code == "ambiguous_multiple_json_objects"


def test_labelled_tool_text_is_normalized_without_semantic_guessing():
    raw = """I need to inspect a repository symbol.
ACTION: tool_call
TOOL: search_repository
ARGUMENTS: {"query":"total_calls","mode":"content","max_results":5}
REASON: Find the call counter access.
"""
    result = normalize_response(raw)
    assert result.strategy == "labelled_text"
    assert result.payload == {
        "action": "tool_call",
        "tool": "search_repository",
        "arguments": {"query": "total_calls", "mode": "content", "max_results": 5},
        "reason": "Find the call counter access.",
    }


def test_labelled_final_text_wraps_only_explicit_diagnosis_object():
    raw = '''ACTION: final
DIAGNOSIS: {"summary":"bounded","root_cause":{},"claims":[],"proposed_corrective_action":"inspect","limitations":[],"next_steps":[]}
'''
    result = normalize_response(raw)
    assert result.strategy == "labelled_text"
    assert result.payload["action"] == "final"
    assert result.payload["diagnosis"]["summary"] == "bounded"


def test_unlabelled_natural_language_is_not_guessed_into_tool_action():
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response("Please search the repository for total_calls and read the adapter.")
    assert exc.value.code == "json_syntax_error"


def test_duplicate_json_keys_are_rejected_even_when_surrounded_by_text():
    raw = 'Response: {"action":"final","action":"tool_call"}'
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response(raw)
    assert exc.value.code == "duplicate_json_key"


def test_nonstandard_json_constants_are_rejected():
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response('{"action":"final","value":NaN}')
    assert exc.value.code == "non_standard_json_constant"


def test_oversized_response_rejected_before_parsing():
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response("x" * 20, max_chars=10)
    assert exc.value.code == "response_too_large"


def test_error_does_not_retain_or_echo_untrusted_response():
    secretish = "PRIVATE_PROVIDER_OUTPUT_928374"
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response(secretish)
    assert secretish not in str(exc.value)


def test_investigator_accepts_labelled_text_action_then_returns_to_canonical_protocol():
    from tests.semantic_audit.test_ae32c_investigator import (
        action_tool,
        final_action,
        make_investigator,
    )

    labelled = """I need to inspect the source.
ACTION: tool_call
TOOL: search_repository
ARGUMENTS: {"query":"observed","mode":"content","max_results":5}
REASON: Locate the relevant implementation.
"""
    investigator, provider, tools = make_investigator([
        labelled,
        final_action(evidence_id="E0002", source_reference=True),
    ])
    report = investigator.run("Investigate the repository issue.")
    assert report["status"] == "completed_with_incomplete_evidence"
    assert [call[0] for call in tools.calls] == ["repository_summary", "search_repository"]
    normalized = [
        event for event in report["errors"]
        if event.get("event") == "provider_response_normalized"
    ]
    assert normalized[0]["strategy"] == "labelled_text"
    assert normalized[0]["surrounding_text"] is True


def test_duplicate_labelled_control_fields_are_rejected():
    raw = """ACTION: tool_call
ACTION: final
TOOL: search_repository
ARGUMENTS: {"query":"x"}
"""
    with pytest.raises(ResponseNormalizationError) as exc:
        normalize_response(raw)
    assert exc.value.code == "duplicate_labelled_field"


def test_labelled_tool_text_accepts_explicit_indented_key_value_arguments():
    raw = """ACTION: tool_call
TOOL: search_repository
ARGUMENTS:
  query: total_calls
  mode: content
  max_results: 5
REASON: Inspect the counter reference.
"""
    result = normalize_response(raw)
    assert result.strategy == "labelled_text"
    assert result.payload["arguments"] == {
        "query": "total_calls",
        "mode": "content",
        "max_results": 5,
    }

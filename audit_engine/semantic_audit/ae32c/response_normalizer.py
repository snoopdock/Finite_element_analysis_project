"""Provider-independent normalization of model responses into the AE-32C action protocol.

The normalizer is deterministic. It accepts strict JSON, fenced/embedded JSON,
and an explicitly labelled text envelope. It never infers a tool invocation
from unlabelled prose and never dispatches tools; downstream validation remains
authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from providers.base import ProviderToolCall
from audit_engine.semantic_audit.ae32c.response_protocol import RESPONSE_TOOL_NAME


@dataclass(frozen=True)
class NormalizationResult:
    payload: dict[str, Any]
    strategy: str
    surrounding_text: bool = False


class ResponseNormalizationError(ValueError):
    """Safe normalization failure; contains no provider-controlled response text."""

    def __init__(self, code: str, *, line: int | None = None, column: int | None = None):
        self.code = code
        self.line = line
        self.column = column
        super().__init__(code)


def _strict_loads(value: str) -> Any:
    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, item in pairs:
            if key in out:
                raise ResponseNormalizationError("duplicate_json_key")
            out[key] = item
        return out

    def reject_constant(_: str) -> None:
        raise ResponseNormalizationError("non_standard_json_constant")

    try:
        return json.loads(value, object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
    except ResponseNormalizationError:
        raise
    except json.JSONDecodeError as exc:
        raise ResponseNormalizationError(
            "json_syntax_error", line=int(exc.lineno), column=int(exc.colno)
        ) from None
    except (TypeError, ValueError):
        raise ResponseNormalizationError("invalid_json_value") from None


def normalize_provider_tool_call(
    tool_call: ProviderToolCall,
    *,
    max_chars: int = 100_000,
) -> NormalizationResult:
    """Convert one provider-native virtual response call to canonical AE-32C JSON.

    The function call is data only. It is not dispatched. The investigator's
    existing action/evidence validators remain authoritative.
    """
    if not isinstance(tool_call, ProviderToolCall):
        raise ResponseNormalizationError("invalid_native_tool_call_type")
    if tool_call.name != RESPONSE_TOOL_NAME:
        raise ResponseNormalizationError("unexpected_native_tool_name")

    arguments = tool_call.arguments
    if isinstance(arguments, str):
        if len(arguments) > max_chars:
            raise ResponseNormalizationError("response_too_large")
        arguments = _strict_loads(arguments)
    if not isinstance(arguments, dict):
        raise ResponseNormalizationError("native_tool_arguments_not_object")

    try:
        serialized = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ResponseNormalizationError("native_tool_arguments_not_json_safe") from None
    if len(serialized) > max_chars:
        raise ResponseNormalizationError("response_too_large")

    required = {"action", "tool", "arguments", "reason", "diagnosis"}
    if set(arguments) != required:
        raise ResponseNormalizationError("native_tool_envelope_shape_invalid")

    action = arguments.get("action")
    tool = arguments.get("tool")
    action_arguments = arguments.get("arguments")
    reason = arguments.get("reason")
    diagnosis = arguments.get("diagnosis")

    if not isinstance(tool, str) or not isinstance(action_arguments, dict):
        raise ResponseNormalizationError("native_tool_action_fields_invalid")
    if not isinstance(reason, str) or not isinstance(diagnosis, dict):
        raise ResponseNormalizationError("native_tool_action_fields_invalid")

    if action == "tool_call":
        if not tool.strip() or not reason.strip() or diagnosis:
            raise ResponseNormalizationError("native_tool_call_action_shape_invalid")
        payload = {
            "action": "tool_call",
            "tool": tool,
            "arguments": action_arguments,
            "reason": reason,
        }
    elif action == "final":
        if tool != "" or action_arguments != {} or reason != "":
            raise ResponseNormalizationError("native_tool_final_action_shape_invalid")
        payload = {"action": "final", "diagnosis": diagnosis}
    else:
        raise ResponseNormalizationError("native_tool_action_not_allowed")

    return NormalizationResult(payload, "native_tool_call", False)


def _one_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResponseNormalizationError("normalized_value_not_object")
    return value


def _balanced_objects(text: str) -> list[str]:
    """Return top-level brace-balanced candidates while respecting JSON strings."""
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:index + 1])
                start = None
    return candidates


def _parse_labelled_arguments(value: str) -> dict[str, Any]:
    """Parse strict JSON arguments or a deliberately small key/value text block."""
    stripped = value.strip()
    if stripped.startswith("{"):
        parsed = _strict_loads(stripped)
        if not isinstance(parsed, dict):
            raise ResponseNormalizationError("labelled_tool_arguments_not_object")
        return parsed

    result: dict[str, Any] = {}
    for line in stripped.splitlines():
        item = line.strip()
        if not item:
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)", item)
        if not match:
            raise ResponseNormalizationError("labelled_tool_arguments_invalid")
        key, raw_value = match.groups()
        if key in result:
            raise ResponseNormalizationError("duplicate_labelled_argument")
        token = raw_value.strip()
        lowered = token.lower()
        if lowered in {"true", "false", "null"}:
            parsed_value: Any = {"true": True, "false": False, "null": None}[lowered]
        else:
            try:
                parsed_value = json.loads(token)
            except (TypeError, ValueError):
                parsed_value = token.strip("\"'")
        result[key] = parsed_value
    if not result:
        raise ResponseNormalizationError("labelled_tool_arguments_invalid")
    return result


def _parse_labelled(text: str) -> dict[str, Any] | None:
    """Parse only explicit ACTION/TOOL/ARGUMENTS or ACTION/DIAGNOSIS labels."""
    lines = text.strip().splitlines()
    labels: dict[str, list[str]] = {}
    declared: dict[str, int] = {}
    current: str | None = None
    for line in lines:
        match = re.match(r"^([A-Z][A-Z0-9_ ]{1,50})\s*:\s*(.*)$", line)
        if match:
            key = re.sub(r"\s+", "_", match.group(1).strip().upper())
            current = key
            declared[key] = declared.get(key, 0) + 1
            labels.setdefault(key, []).append(match.group(2).strip())
        elif current and line.strip():
            labels[current].append(line.strip())

    action_values = labels.get("ACTION", [])
    if not action_values:
        return None
    for critical_key in ("ACTION", "TOOL", "ARGUMENTS", "DIAGNOSIS"):
        if declared.get(critical_key, 0) > 1:
            raise ResponseNormalizationError("duplicate_labelled_field")
    action = action_values[0].strip().lower()
    if action in {"tool_call", "tool", "call_tool"}:
        tool_values = labels.get("TOOL", [])
        args_values = labels.get("ARGUMENTS", [])
        reason_values = labels.get("REASON", [])
        if not tool_values or not args_values:
            raise ResponseNormalizationError("labelled_tool_envelope_incomplete")
        args_text = "\n".join(args_values).strip()
        parsed_args = _parse_labelled_arguments(args_text)
        return {
            "action": "tool_call",
            "tool": tool_values[0].strip(),
            "arguments": parsed_args,
            "reason": "\n".join(reason_values).strip(),
        }
    if action == "final":
        diagnosis_values = labels.get("DIAGNOSIS", [])
        if not diagnosis_values:
            raise ResponseNormalizationError("labelled_final_envelope_incomplete")
        diagnosis_text = "\n".join(diagnosis_values).strip()
        diagnosis = _strict_loads(diagnosis_text)
        if not isinstance(diagnosis, dict):
            raise ResponseNormalizationError("labelled_diagnosis_not_object")
        return {"action": "final", "diagnosis": diagnosis}
    return None


def normalize_response(text: str, *, max_chars: int = 100_000) -> NormalizationResult:
    """Normalize one provider text response to a JSON object without semantic guessing."""
    if not isinstance(text, str):
        raise ResponseNormalizationError("invalid_response_type")
    if not text.strip():
        raise ResponseNormalizationError("empty_response")
    if len(text) > max_chars:
        raise ResponseNormalizationError("response_too_large")

    # Strategy 1: exact strict JSON.
    exact_error: ResponseNormalizationError | None = None
    try:
        return NormalizationResult(_one_object(_strict_loads(text)), "strict_json")
    except ResponseNormalizationError as exc:
        exact_error = exc
        # Duplicate-key and non-standard constants are security-relevant and
        # must not be bypassed by extracting a surrounding object.
        if exc.code in {"duplicate_json_key", "non_standard_json_constant"}:
            raise

    # Strategy 2: one fenced JSON block. A truncated/unclosed fence is still
    # an explicit JSON-format claim and should retain the syntax-error class.
    if text.count("```") == 1:
        # Parse the original response to preserve its stable absolute
        # parser position metadata for existing recovery/report contracts.
        if exact_error is not None:
            raise exact_error
    fences = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
    if len(fences) == 1:
        try:
            return NormalizationResult(_one_object(_strict_loads(fences[0].strip())), "fenced_json", True)
        except ResponseNormalizationError:
            # A single explicit JSON fence is an unambiguous format claim.
            # Preserve its parser error instead of silently reclassifying it.
            raise

    # Strategy 3: deterministic, explicitly labelled text envelope.
    labelled = _parse_labelled(text)
    if labelled is not None:
        return NormalizationResult(labelled, "labelled_text", True)

    # Strategy 4: one unambiguous balanced JSON object embedded in prose.
    candidates = _balanced_objects(text)
    parsed_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            parsed = _strict_loads(candidate)
        except ResponseNormalizationError as exc:
            if exc.code in {"duplicate_json_key", "non_standard_json_constant"}:
                raise
            continue
        if isinstance(parsed, dict):
            parsed_candidates.append(parsed)
    if len(parsed_candidates) == 1:
        return NormalizationResult(parsed_candidates[0], "embedded_json", True)
    if len(parsed_candidates) > 1:
        raise ResponseNormalizationError("ambiguous_multiple_json_objects")

    if exact_error is not None:
        raise exact_error
    raise ResponseNormalizationError("unrecognized_response_format")

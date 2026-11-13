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

from providers.base import ProviderResponse, ProviderToolCall
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

    if set(arguments) == {"action_json"}:
        inner = arguments["action_json"]
        if not isinstance(inner, str) or len(inner) > max_chars:
            raise ResponseNormalizationError("portable_action_json_invalid")
        decoded = _strict_loads(inner)
        return NormalizationResult(
            _one_object(decoded), "native_portable_wire", False
        )

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




_TEXT_EVIDENCE_ID = re.compile(r"^E[0-9]{4,6}$")
_TEXT_SOURCE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _parse_text_evidence_refs(value: str) -> list[str]:
    token = value.strip()
    if token.lower() in {"", "none", "(none)", "[]"}:
        return []
    refs = [item.strip() for item in token.split(",")]
    if not refs or any(not _TEXT_EVIDENCE_ID.fullmatch(item) for item in refs):
        raise ResponseNormalizationError("labelled_final_evidence_refs_invalid")
    if len(set(refs)) != len(refs):
        raise ResponseNormalizationError("labelled_final_evidence_refs_duplicate")
    return refs


def _parse_text_source_reference(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 4:
        raise ResponseNormalizationError("labelled_final_source_reference_invalid")
    evidence_id, path, raw_line, digest = parts
    if not _TEXT_EVIDENCE_ID.fullmatch(evidence_id):
        raise ResponseNormalizationError("labelled_final_source_reference_invalid")
    if not path or len(path) > 500 or path.startswith("/") or "\\" in path:
        raise ResponseNormalizationError("labelled_final_source_reference_invalid")
    if not raw_line.isdigit() or int(raw_line) < 1:
        raise ResponseNormalizationError("labelled_final_source_reference_invalid")
    if not _TEXT_SOURCE_SHA256.fullmatch(digest):
        raise ResponseNormalizationError("labelled_final_source_reference_invalid")
    return {
        "evidence_id": evidence_id,
        "path": path,
        "line": int(raw_line),
        "source_sha256": digest,
    }


def _parse_labelled_final_fields(text: str) -> dict[str, Any] | None:
    """Parse the portable line-oriented final contract without JSON or inference.

    This is intentionally a small grammar. Every field and citation is explicit;
    arbitrary prose is never promoted into a diagnosis or action.
    """
    lines = text.strip().splitlines()
    action_index = next(
        (
            index for index, line in enumerate(lines)
            if re.fullmatch(r"\s*ACTION\s*:\s*final\s*", line, flags=re.I)
        ),
        None,
    )
    if action_index is None:
        return None

    fields: dict[str, str] = {}
    root_sources: list[dict[str, Any]] = []
    limitations: list[str] = []
    next_steps: list[str] = []
    claims: list[dict[str, Any]] = []
    current_claim: dict[str, Any] | None = None
    current_claim_sources: list[dict[str, Any]] = []
    claim_singletons = {
        "CLAIM_STATEMENT",
        "CLAIM_KIND",
        "CLAIM_CONFIDENCE",
        "CLAIM_EVIDENCE_REFS",
    }
    root_singletons = {
        "SUMMARY",
        "ROOT_CAUSE_STATEMENT",
        "ROOT_CAUSE_CONFIDENCE",
        "ROOT_CAUSE_EVIDENCE_REFS",
        "PROPOSED_CORRECTIVE_ACTION",
    }

    for raw_line in lines[action_index + 1:]:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped == "CLAIM_BEGIN":
            if current_claim is not None:
                raise ResponseNormalizationError("labelled_final_claim_nested")
            current_claim = {}
            current_claim_sources = []
            continue
        if stripped == "CLAIM_END":
            if current_claim is None:
                raise ResponseNormalizationError("labelled_final_claim_end_unmatched")
            required_claim = claim_singletons
            if set(current_claim) != required_claim:
                raise ResponseNormalizationError("labelled_final_claim_incomplete")
            statement = current_claim["CLAIM_STATEMENT"].strip()
            kind = current_claim["CLAIM_KIND"].strip().lower()
            confidence = current_claim["CLAIM_CONFIDENCE"].strip().lower()
            evidence_refs = _parse_text_evidence_refs(current_claim["CLAIM_EVIDENCE_REFS"])
            if not statement or kind not in {
                "observation", "hypothesis", "conclusion", "limitation", "recommendation"
            } or confidence not in {"low", "medium", "high"} or not evidence_refs:
                raise ResponseNormalizationError("labelled_final_claim_invalid")
            claims.append({
                "statement": statement,
                "kind": kind,
                "confidence": confidence,
                "evidence_refs": evidence_refs,
                "source_references": current_claim_sources,
            })
            current_claim = None
            current_claim_sources = []
            continue

        match = re.fullmatch(r"([A-Z][A-Z0-9_ ]{1,60})\s*:\s*(.*)", stripped)
        if not match:
            raise ResponseNormalizationError("labelled_final_line_invalid")
        key = re.sub(r"\\s+", "_", match.group(1).strip().upper())
        value = match.group(2).strip()

        if current_claim is not None:
            if key in claim_singletons:
                if key in current_claim:
                    raise ResponseNormalizationError("labelled_final_claim_duplicate_field")
                current_claim[key] = value
            elif key == "CLAIM_SOURCE_REFERENCE":
                if value.lower() not in {"none", "(none)"}:
                    current_claim_sources.append(_parse_text_source_reference(value))
            else:
                raise ResponseNormalizationError("labelled_final_claim_unknown_field")
            continue

        if key in root_singletons:
            if key in fields:
                raise ResponseNormalizationError("labelled_final_duplicate_field")
            fields[key] = value
        elif key == "ROOT_CAUSE_SOURCE_REFERENCE":
            if value.lower() not in {"none", "(none)"}:
                root_sources.append(_parse_text_source_reference(value))
        elif key == "LIMITATION":
            if value.lower() not in {"none", "(none)"}:
                limitations.append(value)
        elif key == "NEXT_STEP":
            if value.lower() not in {"none", "(none)"}:
                next_steps.append(value)
        else:
            raise ResponseNormalizationError("labelled_final_unknown_field")

    if current_claim is not None:
        raise ResponseNormalizationError("labelled_final_claim_unclosed")
    if set(fields) != root_singletons:
        raise ResponseNormalizationError("labelled_final_envelope_incomplete")
    if not claims:
        raise ResponseNormalizationError("labelled_final_claims_empty")

    summary = fields["SUMMARY"].strip()
    root_statement = fields["ROOT_CAUSE_STATEMENT"].strip()
    root_confidence = fields["ROOT_CAUSE_CONFIDENCE"].strip().lower()
    corrective_action = fields["PROPOSED_CORRECTIVE_ACTION"].strip()
    root_evidence_refs = _parse_text_evidence_refs(fields["ROOT_CAUSE_EVIDENCE_REFS"])
    if (
        not summary
        or not root_statement
        or not corrective_action
        or root_confidence not in {"low", "medium", "high"}
        or not root_evidence_refs
    ):
        raise ResponseNormalizationError("labelled_final_root_cause_invalid")

    return {
        "action": "final",
        "diagnosis": {
            "summary": summary,
            "root_cause": {
                "statement": root_statement,
                "confidence": root_confidence,
                "evidence_refs": root_evidence_refs,
                "source_references": root_sources,
            },
            "claims": claims,
            "proposed_corrective_action": corrective_action,
            "limitations": limitations,
            "next_steps": next_steps,
        },
    }


def _parse_labelled(text: str) -> dict[str, Any] | None:
    """Parse explicit tool labels, JSON diagnosis labels, or fielded final text."""
    action_lines = [
        match.group(1).strip().lower()
        for line in text.splitlines()
        if (match := re.fullmatch(r"\s*ACTION\s*:\s*([^\s]+)\s*", line, flags=re.I))
    ]
    has_final_action = action_lines == ["final"]
    has_diagnosis_json = any(
        re.match(r"^\s*DIAGNOSIS\s*:", line, flags=re.I)
        for line in text.splitlines()
    )
    if has_final_action and not has_diagnosis_json:
        return _parse_labelled_final_fields(text)
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
        exact = _one_object(_strict_loads(text))
        if set(exact) == {"action_json"}:
            inner = exact["action_json"]
            if not isinstance(inner, str) or len(inner) > max_chars:
                raise ResponseNormalizationError("portable_action_json_invalid")
            return NormalizationResult(_one_object(_strict_loads(inner)), "portable_wire_json")
        return NormalizationResult(exact, "strict_json")
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
        fielded_final = bool(
            re.search(r"^\s*ROOT_CAUSE_STATEMENT\s*:", text, flags=re.I | re.M)
            and re.search(r"^\s*CLAIM_BEGIN\s*$", text, flags=re.I | re.M)
        )
        return NormalizationResult(
            labelled,
            "labelled_final_text" if fielded_final else "labelled_text",
            True,
        )

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



def normalize_provider_response(
    response: Any,
    *,
    max_chars: int = 100_000,
) -> NormalizationResult:
    """Normalize a provider-neutral response envelope or legacy provider value.

    Native calls take precedence over accompanying text. Multiple native calls,
    unknown function names, and malformed native payloads fail closed rather than
    falling through to potentially conflicting text.
    """
    if isinstance(response, ProviderResponse):
        encoded_parts: list[str] = []
        if response.text is not None:
            encoded_parts.append(response.text)
        for call in response.tool_calls:
            try:
                encoded_parts.append(json.dumps(
                    {"name": call.name, "arguments": call.arguments},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ))
            except (TypeError, ValueError):
                raise ResponseNormalizationError("provider_response_not_json_safe") from None
        if sum(len(part) for part in encoded_parts) > max_chars:
            raise ResponseNormalizationError("response_too_large")
        if response.tool_calls:
            if len(response.tool_calls) != 1:
                raise ResponseNormalizationError("multiple_native_tool_calls")
            if response.text is not None and response.text.strip():
                raise ResponseNormalizationError("ambiguous_provider_response_content")
            return normalize_provider_tool_call(response.tool_calls[0], max_chars=max_chars)
        if response.text is None:
            raise ResponseNormalizationError("empty_response")
        return normalize_response(response.text, max_chars=max_chars)
    if isinstance(response, ProviderToolCall):
        return normalize_provider_tool_call(response, max_chars=max_chars)
    if isinstance(response, str):
        return normalize_response(response, max_chars=max_chars)
    raise ResponseNormalizationError("invalid_response_type")

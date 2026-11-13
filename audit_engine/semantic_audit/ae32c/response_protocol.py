"""Portable function-call envelope used as a response channel by AE-32C.

The function is virtual: providers return its arguments as data. It is never
executed and does not grant access to repository evidence tools.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

RESPONSE_TOOL_NAME = "submit_ae32c_response"

_RESPONSE_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RESPONSE_TOOL_NAME,
        "description": (
            "Submit exactly one AE-32C investigation response. This is a response "
            "format only; it is not an executable repository or external tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Either tool_call or final.",
                },
                "tool": {
                    "type": "string",
                    "description": "For tool_call, the exact registered evidence tool; otherwise empty.",
                },
                "arguments": {
                    "type": "object",
                    "description": "For tool_call, the exact evidence-tool arguments; otherwise an empty object.",
                },
                "reason": {
                    "type": "string",
                    "description": "A concise reason for tool_call; otherwise empty.",
                },
                "diagnosis": {
                    "type": "object",
                    "description": "For final, the complete AE-32C diagnosis; otherwise an empty object.",
                },
            },
            "required": ["action", "tool", "arguments", "reason", "diagnosis"],
        },
    },
}


def build_response_tool_definition() -> dict[str, Any]:
    """Return a fresh OpenAI-compatible function definition."""
    return deepcopy(_RESPONSE_TOOL_DEFINITION)


def response_tool_instruction() -> str:
    """Explain the virtual response function without changing evidence permissions."""
    return (
        "Response-channel instruction: submit exactly one response by calling "
        f"{RESPONSE_TOOL_NAME}. This function is a virtual response envelope only; "
        "it is never executed and is not an evidence tool. Do not call repository "
        "tools through this function. For an evidence action, set action to "
        "'tool_call', set tool to the exact registered evidence-tool name, put its "
        "exact parameters in arguments, provide a non-empty reason, and set "
        "diagnosis to an empty object. For a final response, set action to 'final', "
        "set tool to an empty string, arguments to an empty object, reason to an "
        "empty string, and diagnosis to the complete required diagnosis object. "
        "The investigator independently validates the returned action and enforces "
        "all evidence, permission, and finalization rules."
    )



def response_text_instruction() -> str:
    """Portable text-only fallback instruction for providers without usable structured mode."""
    return (
        "AE-32C plain-text response channel: this request does not provide a native "
        "function-calling or JSON-mode constraint. Do not attempt to call an API or "
        "repository function. Return one response using either a complete canonical "
        "JSON action object or the explicit labelled text contract in the investigation "
        "protocol. For a tool request use ACTION: tool_call, TOOL: exact registered "
        "tool name, ARGUMENTS: a JSON object or one key:value per line, and REASON: "
        "a concise reason. For a final diagnosis, use ACTION: final followed by the "
        "fielded final text contract (SUMMARY, ROOT_CAUSE_STATEMENT, "
        "ROOT_CAUSE_CONFIDENCE, ROOT_CAUSE_EVIDENCE_REFS, optional repeated "
        "ROOT_CAUSE_SOURCE_REFERENCE, one or more CLAIM_BEGIN/CLAIM_END blocks, "
        "PROPOSED_CORRECTIVE_ACTION, optional LIMITATION and NEXT_STEP lines). "
        "Copy evidence IDs and source tuples exactly from supplied evidence. If a "
        "required value is unavailable, state the limitation; never invent it. "
        "The returned action is only a proposal. AE-32C independently validates it "
        "before any evidence tool can be dispatched."
    )


# Transport-friendly strict JSON schema. The nested action is serialized as a
# string to avoid asserting a universal schema for every evidence tool and
# future diagnosis revision. The local AE-32C parser remains authoritative.
_PORTABLE_WIRE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_json": {
            "type": "string",
            "description": "One complete JSON AE-32C tool_call or final action; not executable by the provider.",
        },
    },
    "required": ["action_json"],
    "additionalProperties": False,
}


def build_portable_wire_schema() -> dict[str, Any]:
    return deepcopy(_PORTABLE_WIRE_SCHEMA)


def build_portable_json_schema_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ae32c_response",
            "strict": True,
            "schema": build_portable_wire_schema(),
        },
    }


def build_portable_response_tool_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": RESPONSE_TOOL_NAME,
            "description": "Submit one serialized AE-32C response for local validation; this function is not executed.",
            "parameters": build_portable_wire_schema(),
        },
    }


def portable_wire_instruction() -> str:
    return (
        "AE-32C provider-neutral output: supply exactly one canonical action. "
        "When a strict JSON schema or virtual response function is available, "
        "put the complete serialized action JSON into action_json. Otherwise "
        "you may submit the canonical JSON action directly, or use the "
        "explicit ACTION/TOOL/ARGUMENTS/REASON fielded text contract. "
        "The response channel never executes a function; AE-32C validates "
        "action schema, evidence, permissions, and budgets locally. "
        "Do not invent source references or evidence identifiers."
    )

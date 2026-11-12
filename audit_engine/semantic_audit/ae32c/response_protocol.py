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

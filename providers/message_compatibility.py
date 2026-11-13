"""Pure, transport-neutral message preparation for strict chat templates.

Some serving engines reject more than one `system` role, even when those
messages are contiguous at the beginning. Only the initial system run may be
merged: moving an instruction from the middle of a conversation to the front
would change the trust and temporal meaning of the messages.

Adapters opt into this normalization when their endpoint requires it. The
investigator, source evidence, and action validator remain unchanged.
"""
from __future__ import annotations

from typing import Any


class MessageCompatibilityError(ValueError):
    """A sequence cannot be safely normalized without changing its meaning."""


def coalesce_leading_system_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Return an independent message list with at most one initial system role.

    Returns `(messages, number_of_removed_system_envelopes)`. Only leading
    system messages of the simple `{role, content}` text form can be combined.
    No messages are reordered and no user, assistant, tool, or other content
    is promoted to system authority. Unsupported shapes fail locally.
    """
    if not isinstance(messages, list) or not messages:
        raise MessageCompatibilityError("invalid_chat_messages")
    if any(not isinstance(message, dict) or not isinstance(message.get("role"), str)
           for message in messages):
        raise MessageCompatibilityError("invalid_chat_message_shape")

    leading = 0
    for message in messages:
        if message["role"] != "system":
            break
        leading += 1
    if any(message["role"] == "system" for message in messages[leading:]):
        raise MessageCompatibilityError("noninitial_system_message")

    prepared = [dict(message) for message in messages]
    if leading <= 1:
        return prepared, 0
    for message in prepared[:leading]:
        # A name, cache flag, multimodal part, or vendor extension is not
        # safely representable by plain string concatenation.
        if set(message) != {"role", "content"} or not isinstance(message["content"], str):
            raise MessageCompatibilityError("nonmergeable_system_message")
    combined = "\n\n".join(message["content"] for message in prepared[:leading])
    return [{"role": "system", "content": combined}, *prepared[leading:]], leading - 1

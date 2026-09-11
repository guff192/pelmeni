"""DTO conversion helpers for domain message types."""

from __future__ import annotations

from typing import Any

from pelmeni.domain.messages import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)

_ROLE = "role"
_CONTENT = "content"  # noqa: WPS110
_TOOL_CALLS = "tool_calls"
_TOOL_CALL_ID = "tool_call_id"


def message_to_dto(message: Message) -> dict[str, Any]:
    """Convert a domain Message to a JSON-serialisable dict.

    The produced dict follows the OpenAI Chat Completions shape so
    it can be passed directly to an LLM provider.
    """
    if isinstance(message, SystemMessage):
        return {_ROLE: message.role, _CONTENT: message.content}
    if isinstance(message, UserMessage):
        return {_ROLE: message.role, _CONTENT: message.content}
    if isinstance(message, AssistantMessage):
        return _assistant_to_dto(message)
    if isinstance(message, ToolMessage):
        return {
            _ROLE: message.role,
            _TOOL_CALL_ID: message.tool_call_id,
            _CONTENT: message.content,
        }
    msg = f"Unknown message type: {type(message)!r}"  # noqa: WPS220
    raise TypeError(msg)  # noqa: WPS220


def _assistant_to_dto(
    message: AssistantMessage,
) -> dict[str, Any]:
    """Serialize an AssistantMessage to a DTO dict."""
    dto: dict[str, Any] = {
        _ROLE: message.role,
        _CONTENT: message.content,
    }
    if message.tool_calls:
        dto[_TOOL_CALLS] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": tc.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return dto


def message_from_dto(dto: dict[str, Any]) -> Message:
    """Reconstruct a domain Message from a plain dict.

    Accepts the same OpenAI Chat Completions shape that
    message_to_dto produces.
    """
    role: str = dto[_ROLE]
    if role == "system":
        return SystemMessage(content=dto[_CONTENT])
    if role == "user":
        return UserMessage(content=dto[_CONTENT])
    if role == "assistant":
        return _assistant_from_dto(dto)
    if role == "tool":
        return ToolMessage(
            tool_call_id=dto[_TOOL_CALL_ID],
            content=dto[_CONTENT],
        )
    msg = f"Unknown role: {role!r}"  # noqa: WPS220
    raise ValueError(msg)  # noqa: WPS220


def _assistant_from_dto(
    dto: dict[str, Any],
) -> AssistantMessage:
    """Reconstruct an AssistantMessage from a plain dict.

    Accepts both the normalized internal format (name at top level)
    and the OpenAI provider format (function-wrapped name/arguments).
    """
    raw_calls: list[dict[str, Any]] = dto.get(_TOOL_CALLS) or []
    tool_calls = tuple(
        _tool_call_from_raw(tc)
        for tc in raw_calls
    )
    return AssistantMessage(
        content=dto.get(_CONTENT),
        tool_calls=tool_calls,
    )


def _tool_call_from_raw(tc: dict[str, Any]) -> ToolCall:
    """Parse one tool call dict in either internal or OpenAI format."""
    fn: dict[str, Any] | None = tc.get("function")  # noqa: WPS529
    if fn is not None:
        return ToolCall(
            id=tc["id"],
            name=fn["name"],
            arguments=fn.get("arguments", "{}"),  # noqa: WPS529
        )
    return ToolCall(
        id=tc["id"],
        name=tc["name"],
        arguments=tc["arguments"],
    )

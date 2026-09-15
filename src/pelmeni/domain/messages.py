"""Pure domain message model dataclasses."""

from __future__ import annotations

from dataclasses import dataclass

_ROLE = "role"
_CONTENT = "content"  # noqa: WPS110
_TOOL_CALLS = "tool_calls"
_TOOL_CALL_ID = "tool_call_id"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Represents a single LLM tool-call request."""

    id: str
    name: str
    arguments: str
    thought_signature: str | None = None


@dataclass(frozen=True, slots=True)
class SystemMessage:
    """An LLM system-prompt message."""

    content: str  # noqa: WPS110
    role: str = "system"


@dataclass(frozen=True, slots=True)
class UserMessage:
    """A human user message."""

    content: str  # noqa: WPS110
    role: str = "user"


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    """An LLM assistant response, optionally carrying tool calls."""

    content: str | None = None  # noqa: WPS110
    tool_calls: tuple[ToolCall, ...] = ()
    role: str = "assistant"


@dataclass(frozen=True, slots=True)
class ToolMessage:
    """The result returned for a prior tool call."""

    tool_call_id: str
    content: str  # noqa: WPS110
    role: str = "tool"


Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage

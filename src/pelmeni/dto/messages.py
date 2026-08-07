"""Data transfer objects for messages and tool calls."""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ToolCall(BaseModel):
    """Mirroring OpenAI tool call structure used in loop.py:30-35."""

    id: str
    type: Literal["function"] = "function"
    function: dict[str, str]  # name, arguments (raw string)


class SystemMessage(BaseModel):
    """Mirroring cli.py:17, loop.py:31 roles."""

    role: Literal["system"]
    content: str  # noqa: WPS110


class UserMessage(BaseModel):
    """Mirroring cli.py:17, loop.py:31 roles."""

    role: Literal["user"]
    content: str  # noqa: WPS110


class AssistantMessage(BaseModel):
    """Mirroring loop.py structure, allowing empty content for tool calls."""

    role: Literal["assistant"]
    content: str | None = None  # noqa: WPS110
    tool_calls: list[ToolCall] | None = None
    model_config = ConfigDict(extra="allow")


class ToolMessage(BaseModel):
    """Mirroring loop.py:43 structure for tool results."""

    role: Literal["tool"]
    tool_call_id: str
    content: str  # noqa: WPS110


Message = SystemMessage | UserMessage | AssistantMessage | ToolMessage

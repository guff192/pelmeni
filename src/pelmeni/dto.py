from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# Based on shapes in cli.py, loop.py, tools.py, provider.py, trace.py


class ToolFunction(BaseModel):
    """Mirroring tools.py:33 structure for function definitions."""

    name: str
    description: str
    parameters: dict[str, Any]  # noqa: WPS110


class Tool(BaseModel):
    """Mirroring tools.py:33 structure for function definitions."""

    type: Literal["function"] = "function"
    function: ToolFunction


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


class Choice(BaseModel):
    """Mirroring provider.py:18 message extraction."""

    message: AssistantMessage


class ChatResponse(BaseModel):
    """Mirroring provider.py:18 raw JSON pass-through structure."""

    choices: list[Choice]
    model_config = ConfigDict(extra="allow")


class TraceEvent(BaseModel):
    """Mirroring trace.py:26 payload structure."""

    ts: float
    event: str
    data: dict[str, Any]  # noqa: WPS110
    model_config = ConfigDict(extra="allow")

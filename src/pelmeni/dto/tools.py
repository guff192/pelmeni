"""Data transfer objects for tools and their functions."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """Supported roles for role-aware tool access."""

    INVESTIGATOR = "investigator"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    TESTER = "tester"


class ToolParameterSchema(BaseModel):
    """JSON schema describing the arguments accepted by a tool."""

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """Tool metadata and its optional runtime handler."""

    name: str
    description: str
    parameters: ToolParameterSchema  # noqa: WPS110
    handler: Any = Field(default=None, exclude=True)  # noqa: WPS110


class ToolFunction(BaseModel):
    """Mirroring tools.py:33 structure for function definitions."""

    name: str
    description: str
    parameters: dict[str, Any]  # noqa: WPS110


class Tool(BaseModel):
    """Mirroring tools.py:33 structure for function definitions."""

    type: Literal["function"] = "function"
    function: ToolFunction

"""Data transfer objects for tools and their functions."""
from typing import Any, Literal

from pydantic import BaseModel


class ToolFunction(BaseModel):
    """Mirroring tools.py:33 structure for function definitions."""

    name: str
    description: str
    parameters: dict[str, Any]  # noqa: WPS110


class Tool(BaseModel):
    """Mirroring tools.py:33 structure for function definitions."""

    type: Literal["function"] = "function"
    function: ToolFunction

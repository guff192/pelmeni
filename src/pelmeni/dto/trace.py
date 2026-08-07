"""Data transfer objects for tracing events."""
from typing import Any

from pydantic import BaseModel, ConfigDict


class TraceEvent(BaseModel):
    """Mirroring trace.py:26 payload structure."""

    ts: float
    event: str
    data: dict[str, Any]  # noqa: WPS110
    model_config = ConfigDict(extra="allow")

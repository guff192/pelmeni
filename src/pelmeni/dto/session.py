"""Data transfer objects for session storage and tracing events."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pelmeni.domain.agent_types import AgentType


class TraceEvent(BaseModel):
    """Event record in a JSONL session log."""

    ts: float
    event: str
    data: dict[str, Any] = Field(default_factory=dict)  # noqa: WPS110
    model_config = ConfigDict(extra="allow")


class SessionHeader(BaseModel):
    """Line-1 metadata header record for a session log."""

    event: str = "session_header"
    session_id: str
    workspace: str
    created_at: float
    initial_agent: AgentType = AgentType.REVIEWER
    metadata: dict[str, Any] = Field(default_factory=dict)  # noqa: WPS110
    model_config = ConfigDict(extra="allow")

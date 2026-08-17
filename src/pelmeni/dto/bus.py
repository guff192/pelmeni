"""Data transfer objects for agent bus communication."""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from pelmeni.dto.tools import AgentRole  # noqa: TC001


class AgentStatus(StrEnum):
    """Status of an agent."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class TaskStatus(StrEnum):
    """Status of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageType(StrEnum):
    """Type of a bus message."""

    TASK = "task"
    RESULT = "result"  # noqa: WPS110
    STATUS = "status"
    EVENT = "event"


class TaskPayload(BaseModel):
    """Payload for a task message."""

    task_id: str
    role: AgentRole
    input_data: dict[str, Any] = Field(default_factory=dict)
    context: str | None = None


class ResultPayload(BaseModel):
    """Payload for a result message."""

    task_id: str
    status: TaskStatus
    output: str | None = None
    error: str | None = None


class StatusPayload(BaseModel):
    """Payload for a status message."""

    agent_id: str
    status: AgentStatus
    info: str | None = None  # noqa: WPS110


class BusMessage(BaseModel):
    """Envelope for bus communication."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    msg_type: MessageType
    sender: str
    target: str | None = None
    payload: TaskPayload | ResultPayload | StatusPayload | dict[str, Any]

"""Tests for bus data models and serialization."""

from __future__ import annotations

from pelmeni.dto.bus import (
    AgentStatus,
    BusMessage,
    MessageType,
    ResultPayload,
    StatusPayload,
    TaskPayload,
    TaskStatus,
)
from pelmeni.dto.tools import AgentRole


def test_bus_status_enums() -> None:
    """Status enums define expected string values."""
    assert AgentStatus.IDLE == "idle"
    assert AgentStatus.BUSY == "busy"
    assert AgentStatus.OFFLINE == "offline"

    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.IN_PROGRESS == "in_progress"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"

    assert MessageType.TASK == "task"
    assert MessageType.RESULT == "result"
    assert MessageType.STATUS == "status"
    assert MessageType.EVENT == "event"


def test_task_payload_serialization() -> None:
    """TaskPayload attributes and serialization behavior."""
    payload = TaskPayload(
        task_id="t1",
        role=AgentRole.BUILDER,
        input_data={"key": "val"},
        context="ctx",
    )
    assert payload.task_id == "t1"
    json_str = payload.model_dump_json()
    restored = TaskPayload.model_validate_json(json_str)
    assert restored.task_id == "t1"
    assert restored.role == AgentRole.BUILDER


def test_result_payload_serialization() -> None:
    """ResultPayload attributes and serialization behavior."""
    payload = ResultPayload(
        task_id="t1",
        status=TaskStatus.COMPLETED,
        output="done",
    )
    assert payload.status == TaskStatus.COMPLETED
    json_str = payload.model_dump_json()
    restored = ResultPayload.model_validate_json(json_str)
    assert restored.output == "done"


def test_status_payload_serialization() -> None:
    """StatusPayload attributes and serialization behavior."""
    payload = StatusPayload(
        agent_id="a1",
        status=AgentStatus.IDLE,
        info="ready",
    )
    assert payload.status == AgentStatus.IDLE
    json_str = payload.model_dump_json()
    restored = StatusPayload.model_validate_json(json_str)
    assert restored.info == "ready"


def test_bus_message_envelope_roundtrip() -> None:
    """BusMessage envelope serializes and validates correctly."""
    msg = BusMessage(
        msg_type=MessageType.TASK,
        sender="orchestrator",
        target="builder-1",
        payload={"task_id": "t1"},
    )
    assert msg.id is not None
    assert msg.timestamp > 0
    json_str = msg.model_dump_json()
    restored = BusMessage.model_validate_json(json_str)
    assert restored.sender == "orchestrator"
    assert restored.target == "builder-1"

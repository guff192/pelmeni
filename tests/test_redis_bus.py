"""Tests for RedisBus messaging, queueing, and shared state."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from pelmeni.bus.redis_bus import RedisBus
from pelmeni.dto.bus import BusMessage, MessageType, TaskPayload
from pelmeni.dto.tools import AgentRole


def test_redis_bus_key_formatting() -> None:
    """Keys are correctly namespaced with pelmeni prefix."""
    bus = RedisBus(url="redis://localhost:6379/0")
    assert bus.format_state_key("a1", "status") == "pelmeni:agent:a1:status"
    assert bus.format_task_queue_key("builder") == "pelmeni:queue:builder"
    assert bus.format_channel_key("events") == "pelmeni:channel:events"


def test_redis_bus_publish_mocked() -> None:
    """Publish serializes message and invokes client.publish."""
    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.publish.return_value = 1
        bus._client = mock_client  # noqa: SLF001

        msg = BusMessage(
            msg_type=MessageType.TASK,
            sender="orchestrator",
            target="builder",
            payload={"key": "val"},
        )
        result = await bus.publish("events", msg)
        assert result == 1
        mock_client.publish.assert_called_once()

    asyncio.run(_run())


def test_redis_bus_push_pop_mocked() -> None:
    """Push and pop queue tasks using mocked Redis client."""
    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        task = TaskPayload(
            task_id="t1",
            role=AgentRole.BUILDER,
            input_data={"file": "a.py"},
        )
        mock_client.rpush.return_value = 1
        mock_client.blpop.return_value = (
            b"pelmeni:queue:builder",
            task.model_dump_json().encode("utf-8"),
        )
        bus._client = mock_client  # noqa: SLF001

        pushed = await bus.push_task("builder", task)
        assert pushed == 1

        popped = await bus.pop_task("builder")
        assert popped is not None
        assert popped.task_id == "t1"
        assert popped.role == AgentRole.BUILDER

    asyncio.run(_run())


def test_redis_bus_pop_timeout_returns_none() -> None:
    """Pop task returns None when blpop times out."""
    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.blpop.return_value = None
        bus._client = mock_client  # noqa: SLF001

        result = await bus.pop_task("builder", timeout=1.0)
        assert result is None

    asyncio.run(_run())


def test_redis_bus_pop_invalid_json_returns_none() -> None:
    """Pop task returns None when blpop returns invalid JSON."""
    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.blpop.return_value = (b"queue", b"invalid json")
        bus._client = mock_client  # noqa: SLF001

        result = await bus.pop_task("builder")
        assert result is None

    asyncio.run(_run())


def test_redis_bus_state_mocked() -> None:
    """Set and get agent state using mocked Redis client."""
    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.get.return_value = b"idle"
        bus._client = mock_client  # noqa: SLF001

        await bus.set_state("a1", "status", "idle")
        mock_client.set.assert_called_once_with(
            "pelmeni:agent:a1:status",
            "idle",
        )

        val = await bus.get_state("a1", "status")
        assert val == "idle"

    asyncio.run(_run())

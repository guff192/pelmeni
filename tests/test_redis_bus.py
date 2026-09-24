"""Tests for RedisBus messaging, queueing, and shared state."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

from pelmeni.bus.redis_bus import (
    RedisBus,
    _format_channel_key,
    _format_state_key,
    _format_task_queue_key,
)
from pelmeni.dto.bus import BusMessage, MessageType, TaskPayload
from pelmeni.dto.tools import AgentRole

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator


def test_redis_bus_key_formatting() -> None:
    """Keys are correctly namespaced with pelmeni prefix."""
    assert _format_state_key("a1", "status") == "pelmeni:agent:a1:status"
    assert _format_task_queue_key("builder") == "pelmeni:queue:builder"
    assert _format_channel_key("events") == "pelmeni:channel:events"


def test_redis_bus_publish_mocked() -> None:
    """Publish serializes message and invokes client.publish."""

    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.publish.return_value = 1
        bus._client = mock_client

        msg = BusMessage(
            id="m1",
            timestamp=100.0,
            msg_type=MessageType.EVENT,
            sender="a1",
            payload={"action": "test"},
        )
        sub_count = await bus.publish("general", msg)

        assert sub_count == 1
        mock_client.publish.assert_called_once()

    asyncio.run(_run())


def test_redis_bus_subscribe_mocked() -> None:
    """Subscribe listens on channel and yields deserialized BusMessages."""

    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        msg = BusMessage(
            id="sub_m1",
            timestamp=100.0,
            msg_type=MessageType.EVENT,
            sender="a1",
            payload={"status": "ok"},
        )
        serialized = msg.model_dump_json()

        async def _mock_listen() -> AsyncIterator[dict[str, object]]:
            yield {
                "type": "subscribe",
                "channel": b"pelmeni:channel:updates",
                "data": 1,
            }
            yield {
                "type": "message",
                "channel": b"pelmeni:channel:updates",
                "data": serialized,
            }

        mock_pubsub.listen.side_effect = _mock_listen
        mock_client.pubsub.return_value = mock_pubsub
        bus._client = mock_client

        received: list[BusMessage] = []
        subscriber_gen = cast(
            "AsyncGenerator[BusMessage, None]",
            bus.subscribe("updates"),
        )
        async for incoming in subscriber_gen:
            received.append(incoming)
            break
        await subscriber_gen.aclose()

        assert len(received) == 1
        assert received[0].id == "sub_m1"
        assert received[0].payload == {"status": "ok"}
        mock_pubsub.subscribe.assert_called_once_with("pelmeni:channel:updates")
        mock_pubsub.unsubscribe.assert_called_once_with(
            "pelmeni:channel:updates"
        )
        mock_pubsub.close.assert_called_once()

    asyncio.run(_run())


def test_redis_bus_push_pop_mocked() -> None:
    """Push and pop queue tasks using mocked Redis client."""

    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.rpush.return_value = 1
        bus._client = mock_client

        task = TaskPayload(
            task_id="t1",
            role=AgentRole.BUILDER,
            input_data={"description": "implement feature"},
        )
        qsize = await bus.push_task("builder", task)
        assert qsize == 1

        mock_client.blpop.return_value = (
            b"pelmeni:queue:builder",
            task.model_dump_json().encode("utf-8"),
        )
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
        bus._client = mock_client

        popped = await bus.pop_task("builder")
        assert popped is None

    asyncio.run(_run())


def test_redis_bus_pop_invalid_json_returns_none() -> None:
    """Pop task returns None when blpop returns invalid JSON."""

    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.blpop.return_value = (
            b"pelmeni:queue:builder",
            b"invalid json bytes",
        )
        bus._client = mock_client

        popped = await bus.pop_task("builder")
        assert popped is None

    asyncio.run(_run())


def test_redis_bus_state_mocked() -> None:
    """Set and get agent state using mocked Redis client."""

    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/0")
        mock_client = AsyncMock()
        mock_client.get.return_value = b'{"ready": true}'
        bus._client = mock_client

        await bus.write_state("agent_01", "ready", '{"ready": true}')
        mock_client.set.assert_called_once_with(
            "pelmeni:agent:agent_01:ready",
            '{"ready": true}',
        )

        val = await bus.read_state("agent_01", "ready")
        assert val == '{"ready": true}'

    asyncio.run(_run())

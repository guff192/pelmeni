"""Redis bus implementation for agent communication."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from pydantic import ValidationError
from redis import asyncio as aioredis

from pelmeni.dto.bus import BusMessage, TaskPayload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _format_state_key(agent_id: str, key: str) -> str:
    """Format namespaced Redis key for agent state."""
    return f"pelmeni:agent:{agent_id}:{key}"


def _format_task_queue_key(queue_name: str) -> str:
    """Format namespaced Redis key for task queues."""
    return f"pelmeni:queue:{queue_name}"


def _format_channel_key(channel: str) -> str:
    """Format namespaced Redis key for Pub/Sub channels."""
    return f"pelmeni:channel:{channel}"


def _parse_bus_message(raw_item: dict[str, object]) -> BusMessage | None:
    if raw_item.get("type") != "message":
        return None
    raw_payload = raw_item.get("data")
    if isinstance(raw_payload, bytes):
        raw_payload = raw_payload.decode("utf-8")
    if not isinstance(raw_payload, str):
        return None
    try:
        return BusMessage.model_validate_json(raw_payload)
    except ValidationError:
        return None


def _parse_task_payload(raw_data: bytes | str) -> TaskPayload | None:
    if isinstance(raw_data, bytes):
        raw_data = raw_data.decode("utf-8")
    try:
        return TaskPayload.model_validate_json(raw_data)
    except ValidationError:
        return None


async def _cleanup_pubsub(
    pubsub: aioredis.client.PubSub, channel_key: str
) -> None:
    with contextlib.suppress(Exception):
        await pubsub.unsubscribe(channel_key)
        await pubsub.close()


class RedisBus:
    """Bus interface using Redis Pub/Sub, Lists, and Key-Value state."""

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        """Initialize Redis bus client from URL."""
        self._client: aioredis.Redis = aioredis.from_url(url)

    async def publish(self, channel: str, message: BusMessage) -> int:
        """Publish BusMessage envelope to Pub/Sub channel."""
        channel_key = _format_channel_key(channel)
        pub_result = await self._client.publish(
            channel_key,
            message.model_dump_json(),
        )
        return int(pub_result)

    async def subscribe(
        self,
        channel: str,
    ) -> AsyncIterator[BusMessage]:
        """Subscribe to channel and asynchronously yield incoming messages."""
        channel_key = _format_channel_key(channel)
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel_key)
        try:
            async for raw_message in pubsub.listen():
                parsed = _parse_bus_message(raw_message)
                if parsed is not None:
                    yield parsed
        except BaseException:
            await _cleanup_pubsub(pubsub, channel_key)
            raise
        await _cleanup_pubsub(pubsub, channel_key)

    async def push_task(self, queue_name: str, task: TaskPayload) -> int:
        """Push TaskPayload onto Redis task queue list."""
        queue_key = _format_task_queue_key(queue_name)
        push_result = await self._client.rpush(
            queue_key,
            task.model_dump_json(),
        )
        return int(push_result)

    async def pop_task(
        self,
        queue_name: str,
    ) -> TaskPayload | None:
        """Pop TaskPayload from Redis task queue list."""
        queue_key = _format_task_queue_key(queue_name)
        raw_result = await self._client.blpop([queue_key], timeout=0)
        if raw_result is None:
            return None
        _, raw_data = raw_result
        return _parse_task_payload(raw_data)

    async def write_state(
        self,
        agent_id: str,
        key: str,
        state_value: str,
    ) -> None:
        """Write state string key for agent."""
        state_key = _format_state_key(agent_id, key)
        await self._client.set(state_key, state_value)

    async def read_state(
        self,
        agent_id: str,
        key: str,
    ) -> str | None:
        """Read state string key for agent."""
        state_key = _format_state_key(agent_id, key)
        raw_val = await self._client.get(state_key)
        if raw_val is None:
            return None
        if isinstance(raw_val, bytes):
            return raw_val.decode("utf-8")
        return str(raw_val)

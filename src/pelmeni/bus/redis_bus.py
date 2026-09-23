"""Redis bus implementation for agent communication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError
from redis import asyncio as aioredis

from pelmeni.dto.bus import BusMessage, TaskPayload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# WPS214 method count will be resolved in issue #39
# by encapsulating formatting helpers into private functions.
class RedisBus:  # noqa: WPS214
    """Bus interface using Redis Pub/Sub, Lists, and Key-Value state."""

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        """Initialize Redis bus client from URL."""
        self._client: aioredis.Redis = aioredis.from_url(url)

    def format_state_key(self, agent_id: str, key: str) -> str:
        """Format namespaced Redis key for agent state."""
        return f"pelmeni:agent:{agent_id}:{key}"

    def format_task_queue_key(self, queue_name: str) -> str:
        """Format namespaced Redis key for task queues."""
        return f"pelmeni:queue:{queue_name}"

    def format_channel_key(self, channel: str) -> str:
        """Format namespaced Redis key for Pub/Sub channels."""
        return f"pelmeni:channel:{channel}"

    async def publish(self, channel: str, message: BusMessage) -> int:
        """Publish BusMessage envelope to Pub/Sub channel."""
        client = await self._ensure_client()
        channel_key = self.format_channel_key(channel)
        pub_result = await client.publish(
            channel_key,
            message.model_dump_json(),
        )
        return int(pub_result)

    async def subscribe(
        self,
        channel: str,  # noqa: ARG002
    ) -> AsyncIterator[BusMessage]:
        """Subscribe to Pub/Sub channel (placeholder until issue #39)."""
        err = "RedisBus subscription will be refactored in issue #39"
        raise NotImplementedError(err)
        yield  # noqa: WPS427

    async def push_task(self, queue_name: str, task: TaskPayload) -> int:
        """Push TaskPayload onto Redis task queue list."""
        client = await self._ensure_client()
        queue_key = self.format_task_queue_key(queue_name)
        push_result = await client.rpush(
            queue_key,
            task.model_dump_json(),
        )
        return int(push_result)

    async def pop_task(
        self,
        queue_name: str,
    ) -> TaskPayload | None:
        """Pop TaskPayload from Redis task queue list."""
        client = await self._ensure_client()
        queue_key = self.format_task_queue_key(queue_name)
        raw_result = await client.blpop([queue_key], timeout=0)
        if raw_result is None:
            return None
        _, raw_data = raw_result
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        try:
            return TaskPayload.model_validate_json(raw_data)
        except ValidationError:
            return None

    async def write_state(
        self,
        agent_id: str,
        key: str,
        state_value: str,
    ) -> None:
        """Write state string key for agent."""
        client = await self._ensure_client()
        state_key = self.format_state_key(agent_id, key)
        await client.set(state_key, state_value)

    async def read_state(
        self,
        agent_id: str,
        key: str,
    ) -> str | None:
        """Read state string key for agent."""
        client = await self._ensure_client()
        state_key = self.format_state_key(agent_id, key)
        raw_val = await client.get(state_key)
        if raw_val is None:
            return None
        if isinstance(raw_val, bytes):
            return raw_val.decode("utf-8")
        return str(raw_val)

    async def _ensure_client(self) -> aioredis.Redis:
        return self._client

"""Redis bus implementation for agent communication."""

from __future__ import annotations

import asyncio

from pydantic import ValidationError
from redis.asyncio import Redis, from_url  # noqa: WPS347

from pelmeni.dto.bus import BusMessage, TaskPayload


class RedisBus:  # noqa: WPS214, WPS338
    """Bus interface using Redis Pub/Sub, Lists, and Key-Value state."""

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        """Initialize Redis bus with connection URL."""
        self.url = url
        self._client: Redis | None = None
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Get or create a thread-safe lock for connection management."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def connect(self) -> None:
        """Establish connection to Redis."""
        async with self._get_lock():
            if self._client is None:
                self._client = from_url(self.url)

    async def close(self) -> None:
        """Close connection to Redis."""
        async with self._get_lock():
            if self._client is not None:
                await self._client.aclose()
                self._client = None

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
        timeout: float = 0,  # noqa: ASYNC109
    ) -> TaskPayload | None:
        """Pop TaskPayload from Redis task queue list."""
        client = await self._ensure_client()
        queue_key = self.format_task_queue_key(queue_name)
        raw_result = await client.blpop([queue_key], timeout=timeout)
        if raw_result is None:
            return None
        _, raw_data = raw_result
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        try:
            return TaskPayload.model_validate_json(raw_data)
        except ValidationError:
            return None

    async def set_state(  # noqa: WPS615
        self,
        agent_id: str,
        key: str,
        value: str,  # noqa: WPS110
    ) -> None:
        """Set state string key for agent."""
        client = await self._ensure_client()
        state_key = self.format_state_key(agent_id, key)
        await client.set(state_key, value)

    async def get_state(  # noqa: WPS615
        self,
        agent_id: str,
        key: str,
    ) -> str | None:
        """Get state string key for agent."""
        client = await self._ensure_client()
        state_key = self.format_state_key(agent_id, key)
        raw_val = await client.get(state_key)
        if raw_val is None:
            return None
        if isinstance(raw_val, bytes):
            return raw_val.decode("utf-8")
        return str(raw_val)

    async def _ensure_client(self) -> Redis:
        if self._client is None:
            await self.connect()
        if self._client is None:
            error_message = "Failed to connect Redis client."
            raise RuntimeError(error_message)
        return self._client

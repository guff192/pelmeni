"""In-memory bus implementation supporting Pub/Sub, queues, and state."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from pelmeni.dto.bus import BusMessage, TaskPayload

type SubscriberQueue = asyncio.Queue[Any]


def _reset_stores() -> None:
    """Clear all shared stores across all namespaces."""
    _InMemoryStorage.shared_stores.clear()


class _InMemoryStorage:
    """Internal shared storage container for an in-memory bus namespace."""

    shared_stores: ClassVar[dict[str, _InMemoryStorage]] = {}

    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.queues: dict[str, asyncio.Queue[TaskPayload]] = {}
        self.subscribers: dict[str, set[SubscriberQueue]] = {}

    def get_queue(self, name: str) -> asyncio.Queue[TaskPayload]:
        """Get or initialize named task queue."""
        if name not in self.queues:
            self.queues[name] = asyncio.Queue()
        return self.queues[name]

    @contextlib.contextmanager
    def subscription(
        self,
        channel: str,
    ) -> Generator[SubscriberQueue]:
        """Context manager providing an active subscriber queue."""
        sub_queue: SubscriberQueue = asyncio.Queue()
        if channel not in self.subscribers:
            self.subscribers[channel] = set()
        self.subscribers[channel].add(sub_queue)
        try:
            yield sub_queue
        finally:
            subs = self.subscribers.get(channel)
            if subs is not None:
                subs.discard(sub_queue)
                if not subs:
                    self.subscribers.pop(channel, None)

    def clear(self) -> None:
        """Clear all stored state, queues, and subscribers."""
        self.state.clear()
        self.queues.clear()
        self.subscribers.clear()


def _resolve_namespace(namespace: str, url: str | None) -> str:
    if url and url.startswith(("memory://", "inmemory://")):
        parsed = url.split("://", 1)[1].strip("/")
        return parsed or "default"
    return namespace


def _format_state_key(agent_id: str, key: str) -> str:
    return f"{agent_id}:{key}"


class InMemoryBus:
    """In-memory implementation of the BusProtocol."""

    reset = _reset_stores

    def __init__(
        self,
        namespace: str = "default",
        *,
        isolated: bool = False,
        url: str | None = None,
    ) -> None:
        """Initialize in-memory bus with shared or isolated storage."""
        self.url = url or f"memory://{namespace}"

        if isolated:
            self._storage = _InMemoryStorage()
        else:
            ns_key = _resolve_namespace(namespace, url)
            if ns_key not in _InMemoryStorage.shared_stores:
                _InMemoryStorage.shared_stores[ns_key] = _InMemoryStorage()
            self._storage = _InMemoryStorage.shared_stores[ns_key]

    async def publish(self, channel: str, message: BusMessage) -> int:
        """Publish a message to channel and return count of recipients."""
        subs = self._storage.subscribers.get(channel)
        if not subs:
            return 0

        for sub_queue in list(subs):
            sub_queue.put_nowait(message.model_copy(deep=True))
        return len(subs)

    async def subscribe(
        self,
        channel: str,
    ) -> AsyncIterator[BusMessage]:
        """Subscribe to a channel and asynchronously iterate incoming items."""
        with self._storage.subscription(channel) as sub_queue:
            while True:
                yield await sub_queue.get()

    async def push_task(self, queue_name: str, task: TaskPayload) -> int:
        """Push a task onto named queue and return new length."""
        queue = self._storage.get_queue(queue_name)
        queue.put_nowait(task.model_copy(deep=True))
        return queue.qsize()

    async def pop_task(
        self,
        queue_name: str,
    ) -> TaskPayload | None:
        """Pop task from named queue."""
        queue = self._storage.get_queue(queue_name)
        return await queue.get()

    async def write_state(
        self,
        agent_id: str,
        key: str,
        state_value: str,
    ) -> None:
        """Write agent state in in-memory storage."""
        state_key = _format_state_key(agent_id, key)
        self._storage.state[state_key] = state_value

    async def read_state(
        self,
        agent_id: str,
        key: str,
    ) -> str | None:
        """Read agent state from in-memory storage."""
        state_key = _format_state_key(agent_id, key)
        return self._storage.state.get(state_key)

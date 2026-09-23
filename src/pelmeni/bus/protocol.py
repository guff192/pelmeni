"""Protocol interface defining the common bus operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pelmeni.dto.bus import BusMessage, TaskPayload


@runtime_checkable
class BusProtocol(Protocol):
    """Common bus protocol for agent communication and state sharing."""

    async def publish(self, channel: str, message: BusMessage) -> int:
        """Publish message to channel and return subscriber count."""
        ...

    def subscribe(
        self,
        channel: str,
    ) -> AsyncIterator[BusMessage]:
        """Subscribe to a channel and asynchronously yield incoming messages."""
        ...

    async def push_task(self, queue_name: str, task: TaskPayload) -> int:
        """Push a task onto a named FIFO queue and return the queue length."""
        ...

    async def pop_task(
        self,
        queue_name: str,
    ) -> TaskPayload | None:
        """Pop a task from a named FIFO queue."""
        ...

    async def write_state(
        self,
        agent_id: str,
        key: str,
        state_value: str,
    ) -> None:
        """Write a namespaced key-value state for an agent."""
        ...

    async def read_state(
        self,
        agent_id: str,
        key: str,
    ) -> str | None:
        """Read namespaced key-value state for an agent."""
        ...

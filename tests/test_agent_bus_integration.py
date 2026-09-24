"""Integration tests for RedisBus multi-instance communication."""

from __future__ import annotations

import asyncio
import os
import socket
from typing import TYPE_CHECKING
import uuid

import pytest

from pelmeni.bus.redis_bus import RedisBus
from pelmeni.dto.bus import (
    AgentStatus,
    BusMessage,
    MessageType,
    ResultPayload,
    TaskPayload,
    TaskStatus,
)
from pelmeni.dto.tools import AgentRole

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _is_redis_available(host: str = "127.0.0.1", port: int = 6379) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


REDIS_URL = os.getenv("PELMENI_REDIS_TEST_URL", "redis://localhost:6379/15")
_REDIS_HOST = "localhost" if "localhost" in REDIS_URL else "127.0.0.1"
_REDIS_PORT = 6379

pytestmark = pytest.mark.skipif(
    not _is_redis_available(_REDIS_HOST, _REDIS_PORT),
    reason="Live Redis instance not reachable at localhost:6379",
)


@pytest.fixture
async def clean_redis_buses() -> AsyncIterator[tuple[RedisBus, RedisBus]]:
    """Provide two clean RedisBus instances connected to the test database."""
    bus1 = RedisBus(url=REDIS_URL)
    bus2 = RedisBus(url=REDIS_URL)
    client1 = bus1._client
    await client1.flushdb()
    try:
        yield bus1, bus2
    finally:
        await client1.flushdb()
        await client1.aclose()
        client2 = bus2._client
        await client2.aclose()


def test_orchestrator_worker_task_exchange(
    clean_redis_buses: tuple[RedisBus, RedisBus],
) -> None:
    """Test orchestrator and worker agent exchanging tasks via live RedisBus."""

    async def _run() -> None:
        orchestrator_bus, worker_bus = clean_redis_buses
        orchestrator_id = "orchestrator_001"
        worker_id = "worker_001"
        test_uid = uuid.uuid4().hex[:8]
        task_queue = f"task_queue_{test_uid}"
        task_id = f"test_task_{test_uid}"

        # 1. Orchestrator sets initial state
        await orchestrator_bus.write_state(
            orchestrator_id, "status", AgentStatus.IDLE
        )
        await orchestrator_bus.write_state(
            worker_id, "status", AgentStatus.IDLE
        )
        assert (
            await worker_bus.read_state(orchestrator_id, "status")
            == AgentStatus.IDLE
        )
        assert (
            await orchestrator_bus.read_state(worker_id, "status")
            == AgentStatus.IDLE
        )

        # 2. Orchestrator pushes task to queue
        task_payload = TaskPayload(
            task_id=task_id,
            role=AgentRole.BUILDER,
            input_data={"prompt": "Write a hello world function"},
            context="test context",
        )
        push_result = await orchestrator_bus.push_task(task_queue, task_payload)
        assert push_result == 1

        # 3. Worker pops task from queue
        received_task = await worker_bus.pop_task(task_queue)
        assert received_task is not None
        assert received_task.task_id == task_id
        assert received_task.role == AgentRole.BUILDER

        # 4. Worker updates its status to BUSY
        await worker_bus.write_state(worker_id, "status", AgentStatus.BUSY)
        assert (
            await orchestrator_bus.read_state(worker_id, "status")
            == AgentStatus.BUSY
        )

        # 5. Worker completes task and restores IDLE
        await worker_bus.write_state(worker_id, "status", AgentStatus.IDLE)
        await orchestrator_bus.write_state(
            task_id, "status", TaskStatus.COMPLETED
        )
        assert (
            await orchestrator_bus.read_state(worker_id, "status")
            == AgentStatus.IDLE
        )
        assert (
            await worker_bus.read_state(task_id, "status")
            == TaskStatus.COMPLETED
        )

    asyncio.run(_run())


def test_shared_state_coordination(
    clean_redis_buses: tuple[RedisBus, RedisBus],
) -> None:
    """Test agents coordinating via Redis key-value state."""

    async def _run() -> None:
        bus1, bus2 = clean_redis_buses
        agent_id = f"test_agent_{uuid.uuid4().hex[:8]}"

        await bus1.write_state(agent_id, "status", AgentStatus.IDLE)
        await bus1.write_state(agent_id, "current_task", "none")

        assert await bus2.read_state(agent_id, "status") == AgentStatus.IDLE
        assert await bus2.read_state(agent_id, "current_task") == "none"

        await bus2.write_state(agent_id, "status", AgentStatus.BUSY)
        await bus2.write_state(agent_id, "current_task", "task_123")

        assert await bus1.read_state(agent_id, "status") == AgentStatus.BUSY
        assert await bus1.read_state(agent_id, "current_task") == "task_123"

    asyncio.run(_run())


def test_pubsub_event_communication(
    clean_redis_buses: tuple[RedisBus, RedisBus],
) -> None:
    """Test pub/sub for broadcasting events between real bus instances."""

    async def _run() -> None:
        publisher_bus, subscriber_bus = clean_redis_buses
        channel = f"events_{uuid.uuid4().hex[:8]}"
        sender = "sender_agent"

        event_message = BusMessage(
            id=f"event_{uuid.uuid4().hex[:8]}",
            timestamp=1234567891.0,
            msg_type=MessageType.EVENT,
            sender=sender,
            target=None,
            payload={
                "event_type": "task_completed",
                "task_id": "task_123",
            },
        )

        received_events: list[BusMessage] = []

        async def _consumer() -> None:
            async for msg in subscriber_bus.subscribe(channel):
                received_events.append(msg)
                break

        consumer_task = asyncio.create_task(_consumer())
        await asyncio.sleep(0.1)

        subscribers_count = await publisher_bus.publish(channel, event_message)
        assert subscribers_count >= 1

        await asyncio.wait_for(consumer_task, timeout=2.0)
        assert len(received_events) == 1
        assert received_events[0].id == event_message.id
        assert received_events[0].payload == event_message.payload

    asyncio.run(_run())


def test_full_integration_scenario(
    clean_redis_buses: tuple[RedisBus, RedisBus],
) -> None:
    """Test complete 2-agent scenario with task exchange and result pubsub."""

    async def _run() -> None:
        orchestrator_bus, worker_bus = clean_redis_buses
        test_uid = uuid.uuid4().hex[:8]
        orchestrator_id = "orchestrator_001"
        worker_id = "worker_001"
        task_queue = f"builder_tasks_{test_uid}"
        result_channel = f"task_results_{test_uid}"
        task_id = f"integration_task_{test_uid}"

        task_payload = TaskPayload(
            task_id=task_id,
            role=AgentRole.BUILDER,
            input_data={"code": "print('hello')", "language": "python"},
            context="integration test",
        )

        received_results: list[BusMessage] = []

        async def _orchestrator_listener() -> None:
            async for result_envelope in orchestrator_bus.subscribe(
                result_channel
            ):
                received_results.append(result_envelope)
                break

        listener_task = asyncio.create_task(_orchestrator_listener())
        await asyncio.sleep(0.1)

        # Phase 1: Push task
        await orchestrator_bus.push_task(task_queue, task_payload)

        # Phase 2: Worker retrieves task
        received_task = await worker_bus.pop_task(task_queue)
        assert received_task is not None
        assert received_task.task_id == task_id

        # Phase 3: Worker generates result and publishes
        result_payload = ResultPayload(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            output="def hello():\n    return 'Hello World'",
            error=None,
        )
        result_message = BusMessage(
            id=f"res_{test_uid}",
            timestamp=1234567892.0,
            msg_type=MessageType.RESULT,
            sender=worker_id,
            target=orchestrator_id,
            payload=result_payload,
        )
        await worker_bus.publish(result_channel, result_message)

        # Phase 4: Wait for orchestrator to receive result
        await asyncio.wait_for(listener_task, timeout=2.0)
        assert len(received_results) == 1
        assert received_results[0].sender == worker_id

    asyncio.run(_run())

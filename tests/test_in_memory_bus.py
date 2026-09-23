"""Tests for InMemoryBus and BusProtocol implementation."""

from __future__ import annotations

import asyncio

import pytest

from pelmeni.bus.in_memory import InMemoryBus
from pelmeni.bus.protocol import BusProtocol
from pelmeni.dto.bus import (
    AgentStatus,
    BusMessage,
    MessageType,
    ResultPayload,
    TaskPayload,
    TaskStatus,
)
from pelmeni.dto.tools import AgentRole


def test_in_memory_bus_implements_protocol() -> None:
    """InMemoryBus satisfies BusProtocol interface check."""
    bus = InMemoryBus(isolated=True)
    assert isinstance(bus, BusProtocol)


def test_in_memory_bus_state_management() -> None:
    """State can be set, retrieved, overwritten, and returns None if missing."""

    async def _run() -> None:
        bus = InMemoryBus(isolated=True)
        assert await bus.read_state("agent_1", "status") is None

        await bus.write_state("agent_1", "status", AgentStatus.IDLE)
        assert await bus.read_state("agent_1", "status") == AgentStatus.IDLE

        await bus.write_state("agent_1", "status", AgentStatus.BUSY)
        assert await bus.read_state("agent_1", "status") == AgentStatus.BUSY

        # Another agent key is distinct
        await bus.write_state("agent_2", "status", AgentStatus.OFFLINE)
        assert await bus.read_state("agent_1", "status") == AgentStatus.BUSY
        assert await bus.read_state("agent_2", "status") == AgentStatus.OFFLINE

    asyncio.run(_run())


def test_in_memory_bus_fifo_task_queue() -> None:
    """Tasks are pushed and popped in strict FIFO order across queues."""

    async def _run() -> None:
        bus = InMemoryBus(isolated=True)
        task_1 = TaskPayload(
            task_id="t1",
            role=AgentRole.BUILDER,
            input_data={"work": "build"},
        )
        task_2 = TaskPayload(
            task_id="t2",
            role=AgentRole.BUILDER,
            input_data={"work": "test"},
        )

        # Push tasks and check queue lengths
        len_1 = await bus.push_task("builder_queue", task_1)
        assert len_1 == 1
        len_2 = await bus.push_task("builder_queue", task_2)
        assert len_2 == 2

        # Pop tasks in FIFO order
        popped_1 = await bus.pop_task("builder_queue")
        assert popped_1 is not None
        assert popped_1.task_id == "t1"

        popped_2 = await bus.pop_task("builder_queue")
        assert popped_2 is not None
        assert popped_2.task_id == "t2"

        # Queue is now empty; popping times out
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.01):
                await bus.pop_task("builder_queue")

    asyncio.run(_run())


def test_in_memory_bus_pubsub_fanout_and_isolation() -> None:
    """Pub/sub broadcasts to all subscribers on channel and isolates topics."""

    async def _run() -> None:
        bus = InMemoryBus(isolated=True)

        received_1: list[BusMessage] = []
        received_2: list[BusMessage] = []
        received_other: list[BusMessage] = []

        async def _subscriber_1() -> None:
            async for msg in bus.subscribe("events"):
                received_1.append(msg)
                if len(received_1) == 2:
                    break

        async def _subscriber_2() -> None:
            async for msg in bus.subscribe("events"):
                received_2.append(msg)
                if len(received_2) == 2:
                    break

        async def _subscriber_other() -> None:
            async for msg in bus.subscribe("other_channel"):
                received_other.append(msg)
                break

        task_s1 = asyncio.create_task(_subscriber_1())
        task_s2 = asyncio.create_task(_subscriber_2())
        task_s3 = asyncio.create_task(_subscriber_other())

        # Yield to ensure subscription loops are waiting
        await asyncio.sleep(0.01)

        msg_1 = BusMessage(
            msg_type=MessageType.EVENT,
            sender="agent_1",
            payload={"event": "step_1"},
        )
        msg_2 = BusMessage(
            msg_type=MessageType.EVENT,
            sender="agent_2",
            payload={"event": "step_2"},
        )

        subscribers_count = await bus.publish("events", msg_1)
        assert subscribers_count == 2

        subscribers_count_2 = await bus.publish("events", msg_2)
        assert subscribers_count_2 == 2

        await asyncio.wait_for(asyncio.gather(task_s1, task_s2), timeout=1.0)

        assert len(received_1) == 2
        assert len(received_2) == 2
        assert received_1[0].payload == {"event": "step_1"}
        assert received_2[1].payload == {"event": "step_2"}
        # Other channel received nothing
        assert len(received_other) == 0

        # Cancel remaining listener
        task_s3.cancel()
        await asyncio.gather(task_s3, return_exceptions=True)

    asyncio.run(_run())


def test_in_memory_bus_multi_instance_sharing() -> None:
    """Multiple InMemoryBus instances in namespace share state and queues."""

    async def _run() -> None:
        InMemoryBus.reset()
        bus_a = InMemoryBus(namespace="shared_team")
        bus_b = InMemoryBus(namespace="shared_team")

        # Set state from bus_a, read from bus_b
        await bus_a.write_state("manager", "status", AgentStatus.BUSY)
        assert await bus_b.read_state("manager", "status") == AgentStatus.BUSY

        # Push task from bus_a, pop from bus_b
        task = TaskPayload(
            task_id="team_task",
            role=AgentRole.TESTER,
            input_data={"check": True},
        )
        await bus_a.push_task("team_queue", task)
        popped = await bus_b.pop_task("team_queue")
        assert popped is not None
        assert popped.task_id == "team_task"

        InMemoryBus.reset()

    asyncio.run(_run())


def test_in_memory_bus_multi_agent_e2e() -> None:
    """Full multi-agent workflow runs end-to-end against InMemoryBus."""

    async def _run() -> None:
        bus = InMemoryBus(isolated=True)
        task_queue = "work_queue"
        results_channel = "work_results"

        # 1. Orchestrator sets up agent states
        await bus.write_state("orchestrator", "status", AgentStatus.IDLE)
        await bus.write_state("builder", "status", AgentStatus.IDLE)

        # 2. Worker loop simulating builder
        received_results: list[BusMessage] = []

        async def _worker() -> None:
            # Wait for task
            task = await bus.pop_task(task_queue)
            if task is None:
                return

            await bus.write_state("builder", "status", AgentStatus.BUSY)

            # Do simulated work and publish result
            result_msg = BusMessage(
                msg_type=MessageType.RESULT,
                sender="builder",
                payload=ResultPayload(
                    task_id=task.task_id,
                    status=TaskStatus.COMPLETED,
                    output="Component implemented",
                ),
            )
            await bus.publish(results_channel, result_msg)
            await bus.write_state("builder", "status", AgentStatus.IDLE)

        async def _orchestrator_listener() -> None:
            async for msg in bus.subscribe(results_channel):
                received_results.append(msg)
                break

        listener_task = asyncio.create_task(_orchestrator_listener())
        worker_task = asyncio.create_task(_worker())

        await asyncio.sleep(0.01)

        # 3. Orchestrator pushes task
        task = TaskPayload(
            task_id="feat_42",
            role=AgentRole.BUILDER,
            input_data={"feature": "InMemoryBus"},
        )
        await bus.push_task(task_queue, task)

        await asyncio.wait_for(
            asyncio.gather(worker_task, listener_task),
            timeout=2.0,
        )

        assert len(received_results) == 1
        payload = received_results[0].payload
        assert isinstance(payload, ResultPayload)
        assert payload.output == "Component implemented"
        assert await bus.read_state("builder", "status") == AgentStatus.IDLE

    asyncio.run(_run())

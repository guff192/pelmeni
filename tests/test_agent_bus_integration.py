from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

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


def test_orchestrator_worker_task_exchange() -> None:
    """Test orchestrator and worker agent exchanging tasks via RedisBus."""

    async def _run() -> None:
        # Setup: Two RedisBus instances with mocked clients
        orchestrator_bus = RedisBus(url="redis://localhost:6379/1")
        worker_bus = RedisBus(url="redis://localhost:6379/1")

        # Mock the Redis clients
        mock_orchestrator_client = AsyncMock()
        mock_worker_client = AsyncMock()

        with patch.object(
            orchestrator_bus, "_ensure_client",
            return_value=mock_orchestrator_client,
        ), patch.object(
            worker_bus, "_ensure_client", return_value=mock_worker_client,
        ):
            # Test constants
            orchestrator_id = "orchestrator_001"
            worker_id = "worker_001"
            task_queue = "task_queue"
            result_channel = "task_results"
            task_id = "test_task_123"

            # 1. Orchestrator sets initial state
            await orchestrator_bus.set_state(
                orchestrator_id, "status", AgentStatus.IDLE
            )
            await orchestrator_bus.set_state(
                worker_id, "status", AgentStatus.IDLE
            )
            # Verify state was set
            mock_orchestrator_client.set.assert_any_call(
                f"pelmeni:agent:{orchestrator_id}:status",
                AgentStatus.IDLE,
            )
            mock_orchestrator_client.set.assert_any_call(
                f"pelmeni:agent:{worker_id}:status", AgentStatus.IDLE
            )

            # 2. Orchestrator pushes task to queue
            task_payload = TaskPayload(
                task_id=task_id,
                role=AgentRole.BUILDER,
                input_data={"prompt": "Write a hello world function"},
                context="test context",
            )
            # Mock successful push
            mock_orchestrator_client.rpush.return_value = 1
            push_result = await orchestrator_bus.push_task(
                task_queue, task_payload
            )
            assert push_result == 1

            # 3. Worker pops task from queue
            mock_worker_client.blpop.return_value = (
                orchestrator_bus.format_task_queue_key(task_queue),
                task_payload.model_dump_json(),
            )
            received_task = await worker_bus.pop_task(
                task_queue, timeout=1.0
            )
            assert received_task is not None
            assert received_task.task_id == task_id
            assert received_task.role == AgentRole.BUILDER
            # 4. Worker updates its status to BUSY
            await worker_bus.set_state(
                worker_id, "status", AgentStatus.BUSY
            )
            mock_worker_client.set.assert_called_with(
                f"pelmeni:agent:{worker_id}:status", AgentStatus.BUSY
            )

            # 5. Worker processes task and generates result
            result_payload = ResultPayload(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                output="def hello(): return 'Hello World'",
                error=None,
            )

            result_message = BusMessage(
                id="result_456",
                timestamp=1234567890.0,
                msg_type=MessageType.RESULT,
                sender=worker_id,
                target=orchestrator_id,
                payload=result_payload,
            )

            # 6. Worker publishes result to channel
            mock_worker_client.publish.return_value = 1
            publish_result = await worker_bus.publish(
                result_channel, result_message
            )
            assert publish_result == 1

            mock_worker_client.publish.assert_called_once_with(
                worker_bus.format_channel_key(result_channel),
                result_message.model_dump_json(),
            )

            # 7. Orchestrator receives result and updates task status
            # In real scenario, orchestrator would be subscribed to channel
            # For test, we verify the result was published correctly

            # 8. Worker updates status back to IDLE
            await worker_bus.set_state(
                worker_id, "status", AgentStatus.IDLE
            )
            mock_worker_client.set.assert_called_with(
                f"pelmeni:agent:{worker_id}:status", AgentStatus.IDLE
            )

            # 9. Orchestrator updates task status in shared state
            await orchestrator_bus.set_state(
                task_id, "status", TaskStatus.COMPLETED
            )
            mock_orchestrator_client.set.assert_called_with(
                f"pelmeni:agent:{task_id}:status", TaskStatus.COMPLETED
            )

    asyncio.run(_run())


def test_shared_state_coordination() -> None:
    """Test agents coordinating via Redis key-value state."""

    async def _run() -> None:
        bus = RedisBus(url="redis://localhost:6379/1")
        mock_client = AsyncMock()

        with patch.object(bus, "_ensure_client", return_value=mock_client):
            agent_id = "test_agent"

            # Set initial state
            await bus.set_state(agent_id, "status", AgentStatus.IDLE)
            await bus.set_state(agent_id, "current_task", "none")

            # Verify initial state was set
            mock_client.set.assert_any_call(
                f"pelmeni:agent:{agent_id}:status", AgentStatus.IDLE
            )
            mock_client.set.assert_any_call(
                f"pelmeni:agent:{agent_id}:current_task", "none"
            )

            # Update state as agent becomes busy
            await bus.set_state(agent_id, "status", AgentStatus.BUSY)
            await bus.set_state(agent_id, "current_task", "task_123")

            # Verify updated state was set
            mock_client.set.assert_any_call(
                f"pelmeni:agent:{agent_id}:status", AgentStatus.BUSY
            )
            mock_client.set.assert_any_call(
                f"pelmeni:agent:{agent_id}:current_task", "task_123"
            )

    asyncio.run(_run())


def test_pubsub_event_communication() -> None:
    """Test pub/sub for broadcasting events between agents."""

    async def _run() -> None:
        bus1 = RedisBus(url="redis://localhost:6379/1")
        bus2 = RedisBus(url="redis://localhost:6379/1")

        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()

        with patch.object(bus1, "_ensure_client", return_value=mock_client1), \
             patch.object(bus2, "_ensure_client", return_value=mock_client2):
            channel = "test_events"
            # Mock 2 subscribers receiving the event
            expected_subscriber_count = 2
            sender = "sender_agent"

            # Create event message
            event_message = BusMessage(
                id="event_789",
                timestamp=1234567891.0,
                msg_type=MessageType.EVENT,
                sender=sender,
                target=None,  # Events are broadcast
                payload={
                    "event_type": "task_completed",
                    "task_id": "task_123",
                },
            )

            # Mock successful publish
            mock_client1.publish.return_value = expected_subscriber_count
            result = await bus1.publish(channel, event_message)
            assert isinstance(result, int)
            assert result == expected_subscriber_count

            # Verify publish was called correctly
            mock_client1.publish.assert_called_once_with(
                bus1.format_channel_key(channel),
                event_message.model_dump_json(),
            )

    asyncio.run(_run())


def test_full_integration_scenario() -> None:
    """Test complete 2-agent scenario with task exchange and result handling."""

    async def _run() -> None:
        # Setup buses with mocked clients
        orchestrator_bus = RedisBus(url="redis://localhost:6379/1")
        worker_bus = RedisBus(url="redis://localhost:6379/1")

        mock_orchestrator_client = AsyncMock()
        mock_worker_client = AsyncMock()

        with patch.object(
            orchestrator_bus, "_ensure_client",
            return_value=mock_orchestrator_client,
        ), patch.object(
            worker_bus, "_ensure_client", return_value=mock_worker_client,
        ):
            # Test constants
            orchestrator_id = "orchestrator_001"
            task_queue = "builder_tasks"
            result_channel = "task_results"
            worker_id = "worker_001"
            task_id = "integration_test_456"
            # Phase 1: Orchestrator prepares task
            task_payload = TaskPayload(
                task_id=task_id,
                role=AgentRole.BUILDER,
                input_data={"code": "print('hello')", "language": "python"},
                context="integration test",
            )

            # Mock successful task push
            mock_orchestrator_client.rpush.return_value = 1
            push_result = await orchestrator_bus.push_task(
                task_queue, task_payload
            )
            assert push_result == 1

            # Phase 2: Worker retrieves and processes task
            # Mock task being available on queue
            mock_worker_client.blpop.return_value = (
                worker_bus.format_task_queue_key(task_queue),
                task_payload.model_dump_json(),
            )
            received_task = await worker_bus.pop_task(
                task_queue, timeout=2.0
            )
            assert received_task is not None
            assert received_task.task_id == task_id

            # Worker updates status to BUSY
            await worker_bus.set_state(
                worker_id, "status", AgentStatus.BUSY
            )

            # Phase 3: Worker generates result
            result_payload = ResultPayload(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                output="def hello():\n    return 'Hello World'",
                error=None,
            )

            result_message = BusMessage(
                id="result_789",
                timestamp=1234567892.0,
                msg_type=MessageType.RESULT,
                sender=worker_id,
                target=orchestrator_id,
                payload=result_payload,
            )

            # Mock successful publish
            mock_worker_client.publish.return_value = 1
            publish_result = await worker_bus.publish(
                result_channel, result_message
            )
            assert publish_result == 1

            # Phase 4: Orchestrator processes result
            # In real scenario, orchestrator would receive via pub/sub
            # For test, verify the result was published correctly
            mock_worker_client.publish.assert_called_once_with(
                worker_bus.format_channel_key(result_channel),
                result_message.model_dump_json(),
            )
            # Phase 5: Cleanup - update final states
            await worker_bus.set_state(
                worker_id, "status", AgentStatus.IDLE
            )
            await orchestrator_bus.set_state(
                task_id, "status", TaskStatus.COMPLETED
            )

            # Verify all expected Redis operations occurred
            assert mock_orchestrator_client.rpush.call_count == 1
            assert mock_worker_client.blpop.call_count == 1
            assert mock_worker_client.publish.call_count == 1
            assert mock_orchestrator_client.set.call_count == 1

    asyncio.run(_run())

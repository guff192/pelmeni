# Bus Module and Dual-Adapter Seam Research

This document analyzes the bus transport layer in pelmeni against primary sources in the repository, ADRs, and Issue #32.

## 1. Problem Statement and Primary Source Citations

The current bus implementation binds callers directly to a concrete Redis adapter, exposes storage-specific key formatters on its public interface, and omits the pub/sub subscription interface entirely.

### Primary Source Evidence

1. **Concrete class without an abstract protocol**
   - Source: `src/pelmeni/bus/redis_bus.py:13-17`
   - `RedisBus` is a concrete class taking a Redis connection URL (`url: str = "redis://localhost:6379/0"`).
   - No protocol or abstract base class defines the bus contract. Callers and test suites depend directly on the concrete `RedisBus` symbol.

2. **Storage implementation details leaked into the public interface**
   - Source: `src/pelmeni/bus/redis_bus.py:41-52`
   - The class exposes three public formatting methods:
     - `format_state_key(agent_id: str, key: str) -> str` (line 41)
     - `format_task_queue_key(queue_name: str) -> str` (line 45)
     - `format_channel_key(channel: str) -> str` (line 49)
   - These methods expose Redis-specific key namespacing (`pelmeni:agent:...`, `pelmeni:queue:...`, `pelmeni:channel:...`) to callers.
   - `tests/test_redis_bus.py:13-19` tests these key formatting methods as if they were core behavior rather than internal adapter details.

3. **Missing subscription interface**
   - Source: `src/pelmeni/bus/redis_bus.py:1-124`
   - The docstring on line 14 states: `"Bus interface using Redis Pub/Sub, Lists, and Key-Value state."`
   - The class defines `publish()` on line 53, but provides no `subscribe()` method anywhere in the module.
   - A search across `src/pelmeni/bus/` confirms zero occurrences of `subscribe`.

4. **Integration tests bypass real communication with mock-only assertions**
   - Source: `tests/test_agent_bus_integration.py:181-224`
   - `test_pubsub_event_communication()` creates two `RedisBus` instances (`bus1` and `bus2`).
   - Line 191 patches `_ensure_client` on both instances with `AsyncMock`.
   - Line 213 calls `await bus1.publish(channel, event_message)`.
   - The test never subscribes with `bus2` or receives the published event. `bus2` and `mock_client2` sit unused.
   - Line 218 merely asserts that `mock_client1.publish.assert_called_once_with(...)` was called.
   - Because `RedisBus` lacks a subscription method, tests cannot verify end-to-end event delivery without live Redis or complete client mocking.

5. **Test friction and Docker dependency**
   - Source: `tests/test_redis_bus.py:21-115`, `PLAN.md:10-12` (Issue #32)
   - Every test in `tests/test_redis_bus.py` must manually mock the `Redis` client methods (`publish`, `rpush`, `blpop`, `set`, `get`).
   - Developers and CI environments cannot run multi-agent coordination tests without either mocking Redis methods at low levels or running external Docker containers.

---

## 2. Architectural Analysis: Depth, Seams, and Locality

### The Hypothetical vs Real Seam

Michael Feathers noted that one adapter means a hypothetical seam, while two adapters make a real seam.

Today, the bus seam is hypothetical:
- Only `RedisBus` exists.
- Because only one implementation exists, Redis-specific details (`format_state_key`, `format_task_queue_key`, `format_channel_key`) leaked onto the class interface.
- Callers like `tests/test_agent_bus_integration.py` import `RedisBus` directly and mock Redis client internals.

Introducing `InMemoryBus` alongside `RedisBus` establishes a real seam:
- Both classes satisfy a common `BusProtocol` interface.
- Key formatting, network retries, and Redis connection locks stay private inside `RedisBus`.
- Queue objects and pub/sub subscriber sets stay private inside `InMemoryBus`.
- Callers and tests interact only with the common interface methods.

### Locality Gains

- **Transport locality**: Network connection handling, reconnection locks, and Redis serialization errors concentrate strictly within `RedisBus`.
- **Testing locality**: Multi-agent integration tests run in-process using `InMemoryBus`. Test failures point to agent coordination logic, not to network flakes or mock misconfigurations.
- **Key naming locality**: If key namespacing changes, only `RedisBus` internal methods update. Callers pass logical queue names and agent identifiers directly.

### Leverage Gains

- **Zero-Docker test execution**: Unit and integration test suites run against `InMemoryBus` with zero external dependencies and sub-second execution times.
- **Transparent deployment fallback**: A unified factory function checks Redis availability at startup. If Redis is absent in local development, it returns `InMemoryBus` automatically, preventing startup crashes.
- **Uniform test surface**: Tests and production code cross the exact same seam.

### The Deletion Test

Imagine deleting `RedisBus` mocks from the test suite:
- Currently, deleting the mocks breaks tests because `RedisBus` cannot operate without a Redis server.
- With `InMemoryBus`, the low-level client mocks vanish. Tests run against the in-memory adapter without mock setup boilerplate. Complexity does not move to callers; it disappears.

---

## 3. Structural Specification for the Bus Seam

### BusProtocol Interface

The seam defines an asynchronous protocol containing six core operations:

1. `publish(channel: str, message: BusMessage) -> int`: Broadcasts an envelope to a channel, returning subscriber count.
2. `subscribe(channel: str) -> AsyncIterator[BusMessage]`: Yields messages received on the channel.
3. `push_task(queue_name: str, task: TaskPayload) -> int`: Appends a task to a FIFO queue, returning queue length.
4. `pop_task(queue_name: str, timeout: float | None = None) -> TaskPayload | None`: Pops the next task from a FIFO queue, waiting up to `timeout` seconds.
5. `set_state(agent_id: str, key: str, value: str) -> None`: Stores an agent state string.
6. `get_state(agent_id: str, key: str) -> str | None`: Retrieves an agent state string.
7. `close() -> None`: Cleans up active subscriptions, queues, or network connections.

### Adapter 1: RedisBus

- **Role**: Production distributed adapter for multi-process deployments.
- **Implementation**:
  - Connects to Redis via `redis.asyncio`.
  - Maps channel names, queues, and agent state to namespaced Redis keys internally.
  - Implements `subscribe` via `client.pubsub()`.
  - Keeps formatting helpers (`_format_state_key`, `_format_task_queue_key`, `_format_channel_key`) private.

### Adapter 2: InMemoryBus

- **Role**: In-process adapter for testing, local execution, and offline environments.
- **Implementation**:
  - Task queues backed by `dict[str, asyncio.Queue[TaskPayload]]`.
  - Pub/sub channels backed by `dict[str, set[asyncio.Queue[BusMessage]]]`.
  - State storage backed by `dict[tuple[str, str], str]`.
  - Zero network calls and zero external dependencies.

### Factory Resolution

A single factory function (`create_bus(url: str | None = None, fallback_in_memory: bool = True) -> BusProtocol`):
1. If no URL is provided, returns an `InMemoryBus`.
2. If a URL is provided, attempts a fast ping to Redis.
3. If Redis responds, returns a `RedisBus`.
4. If Redis is unreachable and `fallback_in_memory` is true, logs a warning and returns an `InMemoryBus`.

---

## 4. Primary Source Reference Index

| Finding / Component | Primary Source File | Lines / Section |
| :--- | :--- | :--- |
| Concrete RedisBus Implementation | `src/pelmeni/bus/redis_bus.py` | lines 13–124 |
| Leaked Key Formatting Methods | `src/pelmeni/bus/redis_bus.py` | lines 41–52 |
| Missing Subscribe Method | `src/pelmeni/bus/redis_bus.py` | lines 1–124 (absent) |
| Incomplete Pub/Sub Integration Test | `tests/test_agent_bus_integration.py` | lines 181–224 |
| Mocked Key Formatting Unit Tests | `tests/test_redis_bus.py` | lines 13–19 |
| Mocked Client Operations in Unit Tests | `tests/test_redis_bus.py` | lines 21–115 |
| Bus Models and Payloads | `src/pelmeni/dto/bus.py` | lines 1–68 |
| Common Bus Protocol Spec | `PLAN.md` (Issue #32) | lines 10–12 |
| Multi-Agent Lifecycle Bus Dependency | `PLAN.md` (Issue #23) | lines 36–43 |
| Shared Message Bus Architecture Decision | `docs/adr/0001-no-agent-sdk.md` | lines 1–20 |
| Persistent Agent Sessions over Bus Decision | `docs/adr/0002-persistent-agent-sessions.md` | lines 1–12 |
| Bus & Task Payload Domain Glossary | `CONTEXT.md` | lines 137–139 |

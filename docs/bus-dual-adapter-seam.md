# Technical Decision: Dual-Adapter Agent Bus Seam

## Status
Approved

## Context
Pelmeni requires an inter-agent communication layer capable of supporting:
1. Asynchronous multi-agent execution (Manager, Investigator, Builder, Reviewer, Tester).
2. FIFO task queues for worker roles.
3. Pub/Sub channels for system events and task completion notifications.
4. Shared key-value state for agent status coordination.

Currently, `RedisBus` is the only implemented communication mechanism (`src/pelmeni/bus/redis_bus.py`). While effective for multi-process distributed operation, it introduces an external runtime dependency:
- Multi-agent test suites require a live Redis instance or Docker daemon.
- Contract tests fail in offline CI environments or air-gapped developer workstations.
- New contributors face setup friction when evaluating or building on Pelmeni.

## 1. Concrete Design Seam

The architectural boundary sits at the interface between agent loops (`AgentSession`) and the message transport mechanism:

```
+--------------------------------------------------------+
|                     AgentSession                       |
|   (Manager, Investigator, Builder, Reviewer, Tester)   |
+--------------------------------------------------------+
                           |
                           v
+--------------------------------------------------------+
|                      BusProtocol                       |
|   (publish, subscribe, push_task, pop_task,            |
|    write_state, read_state)                             |
+--------------------------------------------------------+
             |                               |
             v                               v
+------------------------+       +------------------------+
|       RedisBus         |       |      InMemoryBus       |
| (Distributed / Prod)   |       | (Zero-Docker / Test)   |
|                        |       |                        |
| - redis.asyncio        |       | - asyncio.Queue (FIFO) |
| - Redis Pub/Sub        |       | - in-memory pubsub     |
| - Key-value strings    |       | - dict-backed state    |
+------------------------+       +------------------------+
```

### Seam Properties
- **Decoupled from transport**: Callers (`AgentSession`, REPL, test runners) interact strictly with `BusProtocol`.
- **Interchangeable**: `RedisBus` and `InMemoryBus` implement identical method signatures and semantics.
- **Fail-open fallback**: A unified factory function `create_bus()` automatically probes Redis connectivity and falls back to `InMemoryBus` when Redis is unavailable.

## 2. Shared vs. Adapter-Specific Code

### Code That Lives on the Consumer Side (Shared)
- **Data Transfer Objects (`src/pelmeni/dto/bus.py`)**: `BusMessage`, `TaskPayload`, `ResultPayload`, `StatusPayload`, `AgentStatus`, `TaskStatus`, `MessageType`.
- **Bus Interface Protocol (`src/pelmeni/bus/protocol.py`)**: `BusProtocol` specifying the public contract.
- **Bus Factory (`src/pelmeni/bus/factory.py`)**: Unified instantiation logic with connectivity checks.

### Code That Lives in Adapter Implementations (Specific)
- **`RedisBus` (`src/pelmeni/bus/redis_bus.py`)**:
  - Connection pooling and reconnect handling via `redis.asyncio`.
  - Redis key namespacing (`pelmeni:agent:{id}:{key}`, `pelmeni:queue:{name}`, `pelmeni:channel:{name}`).
  - Redis list operations (`rpush`, `blpop`) and Pub/Sub mechanics.
- **`InMemoryBus` (`src/pelmeni/bus/in_memory.py`)**:
  - In-process `asyncio.Queue` management per named task queue.
  - In-process subscriber tracking and broadcasting via async generator iterators.
  - Thread-safe namespaced dictionary for agent state.
  - Namespace isolation and explicit `reset()` capabilities for clean test isolation.

## 3. Structural Specification for the Bus Seam

### BusProtocol Interface

The seam defines an asynchronous protocol containing the six core operations:

1. `publish(channel: str, message: BusMessage) -> int`: Broadcasts an envelope to a channel, returning subscriber count.
2. `subscribe(channel: str) -> AsyncIterator[BusMessage]`: Yields messages received on the channel.
3. `push_task(queue_name: str, task: TaskPayload) -> int`: Appends a task to a FIFO queue, returning queue length.
4. `pop_task(queue_name: str) -> TaskPayload | None`: Pops the next task from a FIFO queue.
5. `write_state(agent_id: str, key: str, state_value: str) -> None`: Stores an agent state string.
6. `read_state(agent_id: str, key: str) -> str | None`: Retrieves an agent state string.

### Adapter 1: RedisBus

- **Role**: Production distributed adapter for multi-process deployments.
- **Implementation**:
  - Connects to Redis via `redis.asyncio`.
  - Maps channel names, queues, and agent state to namespaced Redis keys internally.
  - Implements `subscribe` via `client.pubsub()`.
  - Keeps formatting helpers (`_format_state_key`, `_format_task_queue_key`, `_format_channel_key`) private.

### Adapter 2: InMemoryBus

- **Role**: Zero-dependency adapter for local execution, test suites, and CI.
- **Implementation**:
  - Uses `dict[str, asyncio.Queue]` for FIFO task queues.
  - Uses `dict[str, set[asyncio.Queue]]` for multi-subscriber channel broadcasting.
  - Uses `dict[str, str]` for key-value state.
  - Supports multi-agent testing in offline environments without external containers.

## 4. Factory Resolution Flow

```
create_bus(url=None, force_in_memory=False, timeout=0.5)
  |
  +---> force_in_memory is True?
  |       |
  |       +---> return InMemoryBus()
  |
  +---> url starts with "memory://" or "inmemory://"?
  |       |
  |       +---> return InMemoryBus(url)
  |
  +---> probe Redis at target URL with timeout (default: 500ms)
          |
          +---> Ping succeeded?
          |       |
          |       +---> return RedisBus(target_url)
          |
          +---> Ping failed / connection refused / timed out?
                  |
                  +---> return InMemoryBus(target_url)
```

## Consequences

### Positive
- Contract tests run in milliseconds without launching Docker or spinning up Redis.
- Developer experience is frictionless: `pelmeni` runs out of the box with zero external configuration.
- The boundary enforces clean abstraction: agents cannot depend on Redis-specific features.

### Negative / Trade-offs
- `InMemoryBus` is strictly in-process: multi-process distributed agent topologies require Redis.
- Memory consumption in long-running processes must be monitored if queues or channels are abandoned without consumption.

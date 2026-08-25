# 🤖 pelmeni - Multi-Agent System Technical Documentation

## 🌟 Overview
This document defines the agent structure for **pelmeni**, a multi-agent system built from scratch in Python — no agent SDKs. Each agent is a simple loop over a chat-completions API with role-scoped tools. Specialized agents collaborate to automate different phases of the software development lifecycle, with a focus on minimal context and efficient tool management.

## 🔧 Technology Stack

### Selected Approach: From Scratch, No Agent SDK
The core agent loop is ~100 lines (reference: [chebupelka](https://github.com/alexey-goloburdin/chebupelka)). SDKs hide the message list — the thing we most need to control for our minimal-context strategy — so we own the loop.

**Primary Stack:**
- **Framework**: none — agents are plain Python loops over chat completions (see `src/pelmeni/loop.py`)
- **Language**: Python 3.10+
- **Tooling**: uv for package and Python version management
- **Libraries**: httpx (LLM API calls), Pydantic (message/tool schemas, config validation), Redis (agent bus), FastAPI (only if an HTTP control plane is needed)
- **Use Case**: General-purpose agents, rapid prototyping

## 🔌 LLM Provider Layer

Provider abstraction, not one API. Agents never see providers — they request a model by alias; a router resolves alias → provider + credentials.

### Provider Interface
Each provider is a small client module implementing one interface: `chat(messages, tools, model) -> response`.
- **v1 providers**: OpenAI, Anthropic, Google, plus a generic OpenAI-compatible client (covers Ollama, vLLM, LM Studio, OpenRouter)
- **Auth**: per-provider entry in `~/.config/pelmeni/credentials.toml` (permissions `0600`) with a `type` discriminator; OAuth tokens refreshed automatically
- **Precedence**: env var override (`PELMENI_<PROVIDER>_API_KEY`) → `credentials.toml` → fail fast with a clear "run `pelmeni auth login <provider>`" message
- Credentials never committed; config validated at startup with Pydantic — wrong model alias or missing auth fails fast, not mid-task

### Credentials
`~/.config/pelmeni/credentials.toml` — separate from `config.toml` so the routing config stays shareable/committable. Each entry is a Pydantic discriminated union on `type`:

```toml
[openai]
type = "api_key"
api_key = "sk-..."

[anthropic]
type = "oauth"
access_token = "..."
refresh_token = "..."
expires_at = 1767225600          # unix timestamp; refreshed automatically

[local]                          # openai-compatible, no auth
type = "none"
```

Rules:
- `type` is `Literal["api_key", "oauth", "none"]`; each entry validates against its own schema
- `type = "none"` is explicit for auth-less servers (Ollama etc.) — an absent section means "not configured"
- OAuth entries are machine-managed (written by the device flow, never hand-edited); API-key entries are user-managed
- New auth kinds (e.g. AWS SigV4) are added as new `type` variants without breaking existing files

### Configuration
Single user-editable `config.toml` (safe to commit — no secrets):

```toml
[models]
planner = "anthropic:claude-sonnet-4"     # alias → provider:model
worker  = "openai:gpt-5-mini"
local   = "openai-compatible:qwen3@http://localhost:11434/v1"

[agents]
investigator.model = "local"      # read-only search: cheap/local model
builder.model      = "worker"
reviewer.model     = "planner"
tester.model       = "worker"
```

Rules:
- Per-agent model choice is one line; unset agents fall back to a global default

## 🎯 Context Management Approach

### Minimal Context Strategy
The system implements a minimal context approach to prevent context overflow:

#### Context Isolation
- **Isolated Agent Contexts**: Each agent operates with its own isolated context
- **Minimal Tool Sets**: Agents are provided only with tools relevant to their specific tasks
- **Structured Context Passing**: Context is passed between agents in structured formats

#### Overflow Prevention
- **Automatic Summarization**: Context is automatically summarized to prevent overflow
- **Retention Policies**: Context retention policies ensure only relevant information is maintained
- **Checkpointing**: Agent state is checkpointed for efficient context management

#### Tool Access Control
- **Granular Tool Access**: Tools are assigned to agents based on their role and requirements
- **Role-Based Access**: Different agent types have access to different tool sets
- **Dynamic Tool Loading**: Tools are loaded dynamically as needed

## 🔄 Decision Rationale

### Why No Agent SDK
The decision to build the agent loop from scratch (no LangGraph, no pi SDK) was based on several factors:

#### Clarity and Simplicity
- **The loop is small**: call LLM → run tool calls → append results → repeat. ~100 lines, fully owned
- **No hidden machinery**: every token sent to the model is visible and controllable
- **Model-agnostic**: any OpenAI-compatible or provider-native API works behind our thin provider layer

#### Context Management
- **Byte-level control**: minimal context is our core design principle; SDKs hide exactly the message list we need to manage
- **Own summarization**: context compaction implemented explicitly, tuned per agent role
- **No format lock-in**: SDK message formats would couple agents to a vendor's abstraction

#### Why Not LangGraph Specifically
- LangGraph orchestrates *steps inside one agent* (branching, pause/resume, durable checkpoints)
- Our coordination is *between agents* via a message queue — a different problem a graph framework doesn't solve
- **Escape hatch**: if a single agent later grows complex branching control flow, LangGraph can be adopted inside that agent only, without rewriting the system

#### Development Experience
- **Fewer dependencies**: httpx + Pydantic + Redis is the whole runtime
- **Easy debugging**: plain Python loop, plain logs — no framework internals to trace
- **Learning value**: the team understands every line of the system

## 📚 Libraries and Frameworks

### Core Libraries
- **httpx**: Async HTTP client for LLM provider APIs
- **Pydantic**: Message/tool schemas, structured output, config validation
- **redis-py**: Agent bus (Pub/Sub) and shared state

### Testing and Validation
- **Pytest**: Test framework for agent functionality and tool contracts
- **JSONL trace logs**: Every LLM request/response logged per agent run — observability without SDK lock-in

### Deferred (adopt only when a real need appears)
- **RabbitMQ/Kafka**: If Redis Pub/Sub hits delivery-guarantee limits
- **LangSmith**: If JSONL traces become insufficient for evaluation
- **FastAPI**: If an HTTP control plane is needed

## 🗺️ Development Phases

### Phase 1: Understand Problem
**Purpose**: Agents analyze the problem statement, gather requirements, and identify constraints
**Key Activities**:
- Problem decomposition and scoping
- Requirements gathering and clarification
- Constraint identification and analysis
- Stakeholder needs assessment

### Phase 2: Defining Models
**Purpose**: Agents design data models, domain objects, and system abstractions
**Key Activities**:
- Entity-relationship modeling
- Data structure design
- State management definition
- API contract specification

### Phase 3: Defining Interfaces
**Purpose**: Agents define communication protocols, APIs, and integration points
**Key Activities**:
- API endpoint specification
- Message format definition
- Communication protocol selection
- Integration point identification

### Phase 4: Reviewing
**Purpose**: Agents conduct peer reviews, validate implementations, and ensure quality
**Key Activities**:
- Code review and feedback
- Test case validation
- Performance benchmarking
- Security and compliance checking

## 🛠️ Agent Types

An agent is exactly two things: a **system prompt** and a **tool whitelist**. Roles below differ only in those two fields; the loop, provider layer, and bus wiring are shared. Tool access is enforced by the tool registry, not by convention.

### Investigator Agent
**Role**: Locates code, identifies patterns, finds definitions and references
**Tools**: grep, glob, lsp, read (read-only)
**Output Format**: File-path-first, line-number-attached findings with backticked symbols

### Builder Agent
**Role**: Makes surgical edits to 1-2 files, implements features
**Tools**: edit, write, bash (raw shell, governed by tool hooks — see below)
**Output Format**: Concise change descriptions with verification status

### Reviewer Agent
**Role**: Reviews code for bugs, quality issues, and improvement opportunities
**Tools**: read, grep, lsp (read-only)
**Output Format**: Issue findings with severity levels and suggested fixes

### Tester Agent
**Role**: Creates and executes test cases, validates functionality
**Tools**: bash, write, read
**Output Format**: Test results with pass/fail status and coverage metrics

## 🔄 Development Process

### Development Methodology (TDD)
Preferred way of development is **Test-Driven Development (TDD)**:
- Write failing tests first covering basic expected behavior.
- Implement features/changes to make the tests pass.
- Refactor while keeping tests green.

### Verification Gates
Every change MUST pass all 4 verification gates in this **exact order**:
1. **Pytest** — `.venv/bin/pytest -q tests/`
2. **Mypy** — `.venv/bin/mypy src/pelmeni`
3. **Ruff** — `.venv/bin/ruff check --ignore T201,D107,D102,ANN204,CPY001 src/pelmeni`
4. **Flake8** — `.venv/bin/flake8 src/pelmeni`

### Standard Edit Loop
Standard loop for any edit session, run by the orchestrator (main agent):

1. **Investigation phase** — before every builder edit, spawn an investigator subagent to identify all files in scope of the problem, analyze dependencies (using LSP/grep/glob), and propose possible solutions.
2. **Builder edit** — a builder subagent implements the change based on the investigator's findings.
3. **Style review** — immediately after every builder edit, spawn a reviewer subagent to check code style of the touched files (ruff + flake8/WPS clean, project conventions kept).
4. **Mechanical fix pass** — spawn a new builder-reviewer pair: the builder fixes *only* mechanical issues found in step 3 (line lengths, import order, naming, dead code — single-obvious-way fixes, no design decisions), the reviewer verifies those fixes.
5. **Orchestrator report** — the main agent reports to the user:
   - the list of applied fixes
   - the remaining non-mechanical issues (design choices, complexity refactors, ignore-vs-fix decisions) with options for each

Non-mechanical issues are NEVER fixed without an explicit user decision.
## 🪝 Tool Hooks

Every tool execution passes through a **hook middleware chain** before running. Hooks are a documented, user-customizable interface — not hardcoded checks.

### Hook Interface

```python
hook(tool_call: dict, context: HookContext) -> HookResult
```

`HookResult` is a union object with three possible verdicts:
- **`allow`** — tool call proceeds unchanged
- **`deny`** — tool call blocked; error string returned to the LLM so it can adapt
- **`modify`** — tool call proceeds with a rewritten `tool_call` dict (original untouched); optional metadata (log level, tags) attached for observability

### Hook Context

The `context` parameter carries:
- `agent_role` — the role of the agent making the call (e.g. `"builder"`, `"tester"`)
- `session_id` — unique identifier for the current agent session
- `tool_history` — recent tool calls in this session (for rate-limiting / pattern-matching hooks)

Kept minimal; extend later as real needs appear.

### Built-in Hooks

Three built-in hooks ship with pelmeni:
1. **Command blocklist** — regex patterns blocking destructive commands (`rm -rf /`, `mkfs`, `dd of=/dev/`, fork bombs)
2. **Path guards** — configurable allow/deny path glob patterns with sensible defaults (block writes outside workspace). User overrides patterns in `config.toml`
3. **Confirm-prompt** — publishes a confirmation request to the agent bus; the user can jump into any agent's session (tmux pane in v1) to see the agent's thinking, tool calls, and output, then approve or reject the action. Configurable per-session to auto-allow or auto-deny for unattended runs

### Confirm-Prompt: Session Visibility

The confirm-prompt hook is built on top of the Redis agent bus (build step 5), not blocking stdin:
- Each agent session runs in its own **tmux pane** (v1). The user can attach to any pane to observe the agent's full reasoning and tool calls in real time
- When a hook requires confirmation, it **publishes a confirm request** to the bus. The agent's pane displays the pending action and waits for a response
- The user jumps into the pane, sees full context, and responds `y/n`
- **Bypass modes** (configured per-session in `config.toml`): `confirm = "ask"` (default), `confirm = "always-allow"`, `confirm = "always-deny"`
- **Future**: support for other terminal multiplexers beyond tmux; bus-based confirmation remains the underlying mechanism regardless of UI frontend

### Hook Scope & Filtering

- Hooks apply to **all tools**, not just bash — future tools (grep, read, write, edit) go through the same chain
- Each hook can declare a **tool filter** (list of tool names it cares about). The chain skips hooks whose filter doesn't match the current tool — avoids unnecessary invocations
- Read-only tools still pass through hooks for audit capability, but the default built-in hooks only gate write/execute tools

### Hook Ordering & Chain Behavior

- Hook execution order is an **explicit list** in `config.toml` under `[hooks]`
- **Short-circuit on first deny** — remaining hooks are skipped once any hook denies
- Built-in hooks are listed by default; user hooks are appended or inserted at specific positions

### User-Defined Hooks

- Users add custom hooks as Python modules under `~/.config/pelmeni/hooks/`
- Modules are **declared explicitly** in `config.toml` — only listed modules are loaded (no directory scanning magic)
- Each module must export a `hook()` function matching the hook interface
- Loading via `importlib`; module path resolved relative to `~/.config/pelmeni/hooks/`

### Error Handling

- A hook that raises an exception is treated as **deny** (fail-closed) by default
- The exception is logged with full traceback
- Per-hook `fail_open = true` in `config.toml` overrides to allow — intended for hook development/debugging only

### Configuration Example

```toml
[hooks]
chain = ["blocklist", "path_guard", "confirm_prompt", "my_custom_hook"]

[hooks.path_guard]
allow = ["./src/**", "./tests/**", "./config.toml"]
deny = ["/etc/**", "/usr/**", "~/.ssh/**"]

[hooks.confirm_prompt]
default = "ask"          # "ask" | "always-allow" | "always-deny"

[hooks.my_custom_hook]
module = "audit_log"     # loads ~/.config/pelmeni/hooks/audit_log.py
tools = ["bash", "write"]
fail_open = true         # dev mode: don't block on hook errors
```

### v1 Interim

Until build step 3 is implemented, `tools.py` carries a small hardcoded blocklist (`rm -rf /` class). The hook middleware chain replaces it entirely.

## 🔧 Agent Communication

Agents communicate through Redis:

1. **Message Bus**: Redis Pub/Sub for agent-to-agent and orchestrator-to-agent messaging
2. **Shared State**: Redis keys as the shared knowledge base (task results, artifacts, status)
3. **Tool Results**: Output of one agent becomes input to another via bus messages

### Bus Implementation
- **Channels**: separate channels per message type (tasks, results, status)
- **Durability**: task queues persisted as Redis lists; Pub/Sub for ephemeral status
- **Scale-out options (later)**: RabbitMQ/Kafka, TLS, multi-machine — only if Redis limits are hit

## 🚀 Deployment

### Local-First
- **Environment**: Developer machines
- **Topology**: Orchestrator + agent processes on one machine; Redis via Docker Compose
- **Management**: `docker compose up` for Redis, `uv run` for agents
- **Use Case**: Development, testing, and normal operation

### Future: Cloud
- Containerized agents on K8s, shared Redis/ElastiCache, multi-machine scale-out — designed-for but not built in v1

## 📋 Agent Spawning
> **Note**: The agent spawning workflow and edit loop rules apply to the development and orchestration process of pelmeni itself, not to the runtime behavior of end-user agents executed by pelmeni.


- **Agent definitions**: each agent = config entry (system prompt + tool whitelist + model alias); no discovery directories needed in v1
- **Spawning**: the orchestrator process spawns agents as async tasks or subprocesses, each with isolated context and a bus connection
- **Results**: collected by the orchestrator from the bus and synthesized into the final output

## 🗺️ Build Order

Vertical slice first; each step ends with something runnable:

1. **Core loop + bash tool + one agent** — ✅ done (`src/pelmeni/`): multi-turn REPL session with one agent, bash tool with timeout + temp blocklist, JSONL traces per session
2. **Provider layer + `config.toml`** — ✅ done (`src/pelmeni/`): OpenAI + Anthropic + Google + OpenAI-compatible, per-agent model routing, credential store, Google OAuth device flow, provider facade
3. **Tool hooks** — ✅ done (`src/pelmeni/hooks/`): middleware chain with blocklist, path guards, confirm-prompt
4. **Tool registry + 4 agent types** — ✅ done (`src/pelmeni/tools.py`): role whitelists enforced (`investigator`, `builder`, `reviewer`, `tester`)
5. **Redis bus** — ✅ done (`src/pelmeni/bus/`): two agents talking through Pub/Sub, queues, and shared state
6. **Context compaction baseline** — ✅ done (`src/pelmeni/context/`): `TokenEstimator`, `TruncateCompactor`, and `loop.py` integration with trace events
7. **Pure domain message & round modeling** — ✅ done (`src/pelmeni/domain/`, `src/pelmeni/cli/`): zero-dependency dataclass domain models (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`, `Round`), modular CLI package, and full core cutover
8. **Context compaction hardening (round preservation & output truncation)** — round-based pruning over domain `Round` structures to prevent user prompt starvation, plus head/tail bulky tool output truncation
9. **Everything else** (Kafka, K8s, control-plane API) — only if a real need appears

## 📁 Project Layout

```
src/pelmeni/
├── cli/                    # Modular CLI package (REPL, auth subcommands)
├── loop.py                 # Core agent loop (~50 lines)
├── tools.py                # Tool registry & hook middleware chain
├── trace.py                # Session trace logging
├── bus/                    # Redis async communication bus (Pub/Sub, queues, state)
├── domain/                 # Pure Python zero-dependency domain entities (Messages, Rounds)
├── context/                # Token estimation and context compaction engine
├── dto/                    # Pydantic Data Transfer Objects & hook DTOs
├── auth/                   # Credentials management & Chain of Responsibility resolver
├── hooks/                  # Tool call middleware chain & built-in hooks
├── providers/              # LLM Provider layer, router facade & factory registry
└── config/                 # Pydantic boundary validation schemas & ConfigService facade
```


- **Sessions**: `~/.pelmeni/sessions/<project-name>/<session-hash>/trace.jsonl` — every LLM request/response and tool result
- **Dev model**: local LM Studio server (`localhost:1234`), `qwen/qwen3-8b`; API key is a placeholder constant until step 2

## 🧠 Core Business Logic

### Agent Lifecycle
1. **Initialization**: Agent receives task and context
2. **Execution**: Agent performs assigned work using available tools
3. **Communication**: Agent shares results via agreed-upon mechanisms
4. **Completion**: Agent signals completion and makes results available

### Coordination Patterns
- **Pipeline**: Output of one agent becomes input to next
- **Parallel**: Multiple agents work simultaneously on different aspects
- **Feedback Loop**: Agents review and refine each other's work
- **Consensus**: Multiple agents validate critical decisions

## 📱 Communication Tone
- **Style**: Technical, precise, action-oriented
- **Audience**: Developer-to-developer communication
- **Format**: Structured, scannable, minimal corporate jargon


## 🔄 Recent Updates & Module Refactoring

The project architecture underwent a comprehensive modular refactoring to eliminate flat file clutter, enforce clean design patterns, and maintain 100% compliance with WPS / Flake8 / Ruff / Mypy / Pytest rules:

### 1. Data Transfer Objects (`src/pelmeni/dto/`)
- Centralized all Pydantic DTO models across `credentials.py`, `messages.py`, `responses.py`, `tools.py`, and `trace.py`.
- Credentials DTOs (`ApiKeyCredentials`, `OAuthCredentials`, `NoCredentials`) handle boundary serialization and discriminated union parsing.

### 2. Authentication & Resolver (`src/pelmeni/auth/`)
- Refactored authentication and credential resolution into a dedicated `auth/` package.
- **Chain of Responsibility Pattern** implemented in `src/pelmeni/auth/resolver.py`:
  - `AbstractCredentialHandler(ABC)` with fluent `.set_next(target_link)` method chaining.
  - Sequential resolution chain: `EnvVarHandler` → `TomlStoreHandler` → `NoAuthHandler`.
  - `AuthManager` facade (`manager.py`) manages interactive logins and store operations.
- `store.py` enforces strict `0600` permissions on `~/.config/pelmeni/credentials.toml`.

### 3. LLM Provider Layer & Router (`src/pelmeni/providers/`)
- Organized provider subsystem under `src/pelmeni/providers/`:
  - **Facade Pattern**: `ProviderRouter` (`router.py`) maps model aliases to provider clients.
  - **Registry / Factory Pattern**: `ProviderFactory` (`factory.py`) creates provider instances.
  - Sub-packages `anthropic/` and `google/` isolate request/response formatting logic from main provider adapters.

### 4. Configuration Sub-system (`src/pelmeni/config/`)
- Structured `config/` package:
  - `models.py`: Pydantic boundary validation schemas (`AppConfigSchema`, `AgentModelSchema`, `ModelSpec`) for `config.toml`.
  - `parser.py`: TOML loader & parser routines.
  - `service.py`: `ConfigService` facade & `AppConfig` runtime value object.

### 5. Tool Hooks Middleware (`src/pelmeni/hooks/`)
- **Build Step 3 Complete**: Replaced hardcoded bash regex blocklist with a fully configurable, extensible hook middleware chain (`HookChain`).
- **Protocol & DTOs**: Structural `Hook` protocol (`protocol.py`), immutable `HookContext` and `HookResult` value objects (`dto/hooks.py`).
- **Built-in Hooks** (`builtins.py`):
  - `BlocklistHook`: migrated and expanded destructive pattern matching.
  - `PathGuardHook`: configurable file path boundary guards using glob patterns.
  - `ConfirmPromptHook`: pluggable human-in-the-loop confirmation (ask, always-allow, always-deny, stdin fallback).
- **Dynamic Loading & Config** (`loader.py`): chain order configured in `config.toml` under `[hooks.chain]`; loads user-defined Python module hooks from `~/.config/pelmeni/hooks/` via `importlib.util`.
- **Wiring & Dispatch**: `tools.dispatch()` gates all tool execution through `HookChain.run()`; `loop.run()` propagates context and history; `cli.py` initializes config-driven hooks.

### 6. Quality & Verification Gates
- **Pytest**: 100% test coverage green (79 passed tests).
- **Mypy**: Strict static typing passes (0 errors across source files).
- **Ruff & Flake8**: 0 diagnostics / 0 WPS violations across the entire codebase.

### 7. Tool Registry & 4 Agent Types Subsystem (`src/pelmeni/tools.py`, `src/pelmeni/dto/tools.py`)
- **Build Step 4 Complete**: Implemented domain-level tool registry and role-based tool whitelisting for 4 agent types.
- **DTOs & Roles**: Defined `AgentRole` enum (`investigator`, `builder`, `reviewer`, `tester`), `ToolParameterSchema`, and `ToolSpec` in `src/pelmeni/dto/tools.py`.
- **ToolRegistry & Permission Gating**:
  - `ToolRegistry` manages tool specifications and role-specific whitelists.
  - `get_serialized_tools(role)` generates provider-compatible function tool schemas for role-permitted tools.
  - `tools.dispatch()` enforces role permission checks before hook middleware execution.
- **Loop & Config Integration**:
  - `loop.run()` passes role-filtered tool schemas to `provider.chat()` and forwards `registry` to `dispatch()`.
  - `AgentModelSchema` in `src/pelmeni/config/models.py` supports optional `tools: list[str]` overrides per role.
- **Test Suite**: Added contract test suites in `tests/test_tool_models.py` and `tests/test_tool_interfaces.py` (64 total tests passing).

### 8. Redis Bus & Multi-Agent Communication Subsystem (`src/pelmeni/bus/`, `src/pelmeni/dto/bus.py`)
- **Build Step 5 Complete**: Implemented async Redis messaging bus for multi-agent coordination.
- **Domain DTOs & Enums**:
  - Enums: `AgentStatus` (`idle`, `busy`, `offline`), `TaskStatus` (`pending`, `in_progress`, `completed`, `failed`), `MessageType` (`task`, `result`, `status`, `event`).
  - Payloads: `TaskPayload`, `ResultPayload`, `StatusPayload`, and polymorphic envelope `BusMessage`.
- **RedisBus Adapter (`src/pelmeni/bus/redis_bus.py`)**:
  - Async engine using `redis.asyncio` with `asyncio.Lock` lifecycle management.
  - **Pub/Sub**: `publish(channel, message)` for broadcasting events and results.
  - **Task Queues**: `push_task(queue, task)` and `pop_task(queue, timeout)` with `ValidationError` protection against malformed payloads.
  - **Shared State**: `set_state(agent_id, key, val)` and `get_state(agent_id, key)` with transparent namespacing (`pelmeni:agent:*`, `pelmeni:queue:*`, `pelmeni:channel:*`).
- **Configuration Integration**:
  - `RedisSchema` added to `config/models.py` and `AppConfig` with default connection URL.
- **End-to-End Multi-Agent Integration**:
  - Added `tests/test_agent_bus_integration.py` proving orchestrator and worker task delegation, result Pub/Sub, and state coordination (79 total tests passing).

### 9. Context Compaction Subsystem (`src/pelmeni/context/`, `src/pelmeni/dto/context.py`)
- **Build Step 6 Complete**: Implemented modular context compaction engine to prevent token budget exhaustion.
- **Domain DTOs & Config**:
  - `CompactionStrategy` enum (`truncate`, `summarize`), `CompactionResult`, and `CompactionConfigSchema` in `src/pelmeni/dto/context.py`.
  - `CompactionConfigSchema` wired into `AgentModelSchema` and `AppConfigSchema` with per-agent override resolution in `ConfigService`.
- **Protocols & Engine**:
  - `TokenEstimator` protocol with `HeuristicEstimator` implementation (deterministic character/JSON calculation).
  - `ContextCompactor` protocol with `TruncateCompactor` implementation.
  - Re-exports centralized in `src/pelmeni/context/__init__.py`.
- **Loop Integration (`src/pelmeni/loop.py`)**:
  - Compaction runs at the start of each iteration before the LLM request.
  - In-place mutation of `messages` list (`messages[:] = ...`).
  - Trace observability logging `context_compacted` events.
- **Observed Edge Cases & Build Step 7 Target**:
  - *User prompt preservation*: Naive sequential popping from index 1 removes user prompts, leaving broken `['system', 'assistant', 'tool']` sequences that cause LLM hallucination/errors.
  - *Oversize tool output truncation*: When a single tool output (e.g. 26KB `cat ./AGENTS.md`) exceeds `target_tokens`, dropping short user messages cannot resolve context pressure. Intermediate tool outputs must support content truncation.

### 10. Pure Domain Message Modeling & Modular CLI (`src/pelmeni/domain/`, `src/pelmeni/cli/`)
- **Build Step 7 Complete**: Introduced zero-dependency domain entities and completed full core cutover away from loose `dict[str, Any]`.
- **Pure Domain Dataclasses (`src/pelmeni/domain/`)**:
  - `ToolCall`, `SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage` implemented as `@dataclass(frozen=True, slots=True)` with zero external dependencies.
  - `Round` aggregate encapsulating user prompt and associated assistant/tool turns.
  - `group_into_rounds()` partitioning message sequences into `(system_prompt, list[Round])`.
  - `message_mappers.py` providing bidirectional conversions between domain entities and OpenAI wire DTOs.
- **Core & Context Cutover**:
  - `src/pelmeni/loop.py` manages `list[Message]` and performs boundary wire translation immediately before `provider.chat()`.
  - `src/pelmeni/tools.py` provides `dispatch_and_append()` emitting domain `ToolMessage` instances.
  - `src/pelmeni/context/` protocols and compactor operate over `list[Message]`.
- **Modular CLI Package & Linter Hardening**:
  - Restructured `src/pelmeni/cli/` (`main.py`, `repl.py`, `auth.py`) eliminating `# flake8: noqa: WPS201`.
  - Loop imports streamlined via package facades, eliminating WPS201 across the core loop.
  - 100% test coverage green (165 total tests passing).
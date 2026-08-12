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

1. **Builder edit** — a builder subagent makes the requested change.
2. **Style review** — immediately after every builder edit, spawn a reviewer subagent to check code style of the touched files (ruff + flake8/WPS clean, project conventions kept).
3. **Mechanical fix pass** — spawn a new builder-reviewer pair: the builder fixes *only* mechanical issues found in step 2 (line lengths, import order, naming, dead code — single-obvious-way fixes, no design decisions), the reviewer verifies those fixes.
4. **Orchestrator report** — the main agent reports to the user:
   - the list of applied fixes
   - the remaining non-mechanical issues (design choices, complexity refactors, ignore-vs-fix decisions) with options for each

Non-mechanical issues are NEVER fixed without an explicit user decision.
## 🪝 Tool Hooks

Every tool execution passes through a **hook middleware chain** before running. Hooks are a documented, user-customizable interface — not hardcoded checks.

- **Interface**: `hook(tool_call, context) -> allow | deny | modify`
- **Built-in hooks**: command blocklist (e.g. `rm -rf /`), path guards (writes restricted to the workspace), confirm-prompt (ask the user y/n before risky commands)
- **Customization**: users add hooks in `config.toml` or as Python modules under `~/.config/pelmeni/hooks/`; ordering is explicit
- **Applies to all tools**, but the primary motivation is governing raw `bash` access for Builder and Tester agents
- **v1 interim**: until step 3, `tools.py` carries a small hardcoded blocklist (`rm -rf /` class)

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

- **Agent definitions**: each agent = config entry (system prompt + tool whitelist + model alias); no discovery directories needed in v1
- **Spawning**: the orchestrator process spawns agents as async tasks or subprocesses, each with isolated context and a bus connection
- **Results**: collected by the orchestrator from the bus and synthesized into the final output

## 🗺️ Build Order

Vertical slice first; each step ends with something runnable:

1. **Core loop + bash tool + one agent** — ✅ done (`src/pelmeni/`): multi-turn REPL session with one agent, bash tool with timeout + temp blocklist, JSONL traces per session
2. **Provider layer + `config.toml`** — ✅ done (`src/pelmeni/`): OpenAI + Anthropic + Google + OpenAI-compatible, per-agent model routing, credential store, Google OAuth device flow, provider facade
3. **Tool hooks** — middleware chain with blocklist, path guards, confirm-prompt
4. **Tool registry + 4 agent types** — role whitelists enforced
5. **Redis bus** — two agents talking through Pub/Sub
6. **Context compaction** — summarize old messages when over token budget
7. **Everything else** (Kafka, K8s, control-plane API) — only if a real need appears

## 📁 Project Layout

```
src/pelmeni/
  provider.py   # raw httpx to OpenAI-compatible /chat/completions (constants for now; config.toml in step 2)
  tools.py      # bash tool: schema, dispatch, timeout, temp blocklist guard
  loop.py       # the agent loop: chat -> tool calls -> append -> repeat, 25-iteration cap
  trace.py      # JSONL session traces
  cli.py        # multi-turn REPL entry point (`uv run pelmeni`)
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

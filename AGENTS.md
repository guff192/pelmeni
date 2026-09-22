# 🤖 Pelmeni - Agent Operational Manual

Operational reference for coding agents working on **pelmeni**. For domain terminology, see `CONTEXT.md`. For architecture decisions and trade-offs, see `docs/adr/`.

---

## 🔧 Technology Stack

- **Framework**: Plain Python loop over chat completions (`src/pelmeni/loop.py`), no agent framework SDKs.
- **Language & Runtime**: Python 3.10+, managed with `uv`.
- **Core Dependencies**:
  - `httpx` — async HTTP client for provider APIs.
  - `pydantic` — data schemas, boundary validation, configuration.
  - `redis.asyncio` — agent message bus, task queues, shared state.
- **Verification Tooling**: `pytest`, `mypy`, `ruff`, `flake8` (with `wemake-python-styleguide`).

---

## 🔌 LLM Provider Layer

Agents request models by alias. A provider router resolves `alias -> provider:model` and loads credentials.

### Provider Interface
Every provider client implements:
```python
chat(messages: list[Message], tools: list[ToolSpec] | None, model: str) -> Response
```
Supported providers: OpenAI, Anthropic, Google, OpenAI-compatible (Ollama, vLLM, LM Studio, OpenRouter, Antigravity).

### Authentication Precedence
1. Environment variable: `PELMENI_<PROVIDER>_API_KEY`
2. Credentials store: `~/.config/pelmeni/credentials.toml` (permissions `0600`)
3. Fail-fast error instructing the user to configure credentials.

### Credentials (`~/.config/pelmeni/credentials.toml`)
Discriminated union on `type` (`api_key`, `oauth`, `none`):

```toml
[openai]
type = "api_key"
api_key = "sk-..."

[anthropic]
type = "oauth"
access_token = "..."
refresh_token = "..."
expires_at = 1767225600

[local]
type = "none"
```

### Configuration (`config.toml`)
Maps aliases and assigns models to agent roles:

```toml
[models]
planner = "anthropic:claude-sonnet-4"
worker  = "openai:gpt-5-mini"
local   = "openai-compatible:qwen3@http://localhost:11434/v1"

[agents]
investigator.model = "local"
builder.model      = "worker"
reviewer.model     = "planner"
tester.model       = "worker"
```

---

## 🛠️ Agent Roles & Tool Whitelists

An agent profile consists of a system prompt, a tool whitelist, and a model alias. Tool permissions are strictly enforced by `ToolRegistry` (`src/pelmeni/tools/registry.py`), never by convention or prompting.

| Role | Allowed Tools | Responsibilities | Output Format |
|---|---|---|---|
| **Investigator** | `read`, `grep`, `glob`, `lsp` | Locate code, analyze references and dependencies (strictly read-only). | File-path-first, line-numbered findings with backticked symbols. |
| **Builder** | `read`, `edit`, `write`, `bash` | Surgical code edits to 1–2 files, feature implementation. | Concise change descriptions with verification status. |
| **Reviewer** | `read`, `grep`, `lsp`, `bash` | Audit diffs for bugs, quality, and style adherence. | Issue findings tagged as `[MECHANICAL]` or `[NON-MECHANICAL]`. |
| **Tester** | `read`, `write`, `bash` | Author and execute test cases, validate behavior against requirements. | Test run results, pass/fail status, and coverage metrics. |

---

## 🪝 Tool Hooks & Security

Every tool execution passes through a hook middleware chain (`src/pelmeni/hooks/`) before execution.

### Hook Interface
```python
hook(tool_call: dict[str, Any], context: HookContext) -> HookResult
```

- **Verdicts (`HookResult`)**:
  - `allow` — tool execution proceeds unchanged.
  - `deny` — execution blocked; error message returned to model.
  - `modify` — rewritten tool arguments passed to execution.
- **`HookContext`**: carries `agent_role`, `session_id`, and `tool_history`.

### Built-in Hooks
1. **`blocklist`** — regex matching against destructive shell commands (`rm -rf /`, `mkfs`, fork bombs).
2. **`path_guard`** — glob allow/deny matching preventing file operations outside workspace boundaries.
3. **`confirm_prompt`** — human-in-the-loop approval gate (`ask`, `always-allow`, `always-deny`).
4. **`gitignore_guard`** — prompts user confirmation before accessing `.gitignore`-matched paths.

### Hook Execution Rules
- Execution follows the order in `config.toml` under `[hooks.chain]`.
- **Short-circuit**: evaluation stops on the first `deny`.
- **Fail-closed**: an unhandled exception in a hook produces `deny` unless `fail_open = true` is set.

```toml
[hooks]
chain = ["blocklist", "path_guard", "confirm_prompt", "gitignore_guard"]

[hooks.path_guard]
allow = ["./src/**", "./tests/**", "./config.toml"]
deny = ["/etc/**", "/usr/**", "~/.ssh/**"]

[hooks.confirm_prompt]
default = "ask"
```

---

## 🔄 Development Process

### Development Methodology (TDD)
1. Write failing tests first covering expected behavior.
2. Implement minimum required changes to make tests pass.
3. Refactor while keeping test suite green.

### Verification Gates
Every change MUST pass all four verification gates in this exact order:
```bash
.venv/bin/pytest -q tests/
.venv/bin/mypy src/pelmeni
.venv/bin/ruff check --ignore T201,D107,D102,ANN204,CPY001 src/pelmeni
.venv/bin/flake8 src/pelmeni
```

### Standard Edit Loop
1. **Investigation Phase**: Spawn `investigator` to locate relevant files, analyze dependencies, and propose solutions.
2. **Builder Edit**: Spawn `builder` to implement changes based on investigator findings.
3. **Style Review**: Spawn `reviewer` to verify ruff and flake8/WPS cleanliness on touched files.
4. **Mechanical Fix Pass**: Spawn `builder` to fix *only* mechanical issues (`reviewer` verifies).
5. **Report to User**: Report applied fixes and list non-mechanical issues with options.
   - Non-mechanical issues (design decisions, complexity refactoring) are NEVER altered without explicit user decision.

---

## 📁 Project Layout

```
src/pelmeni/
├── auth/         # Credentials management & Chain of Responsibility resolver
├── bus/          # Redis async message bus (Pub/Sub, queues, state)
├── cli/          # Modular CLI commands (REPL, auth, tools-mcp)
├── config/       # Pydantic configuration schemas & ConfigService
├── context/      # Token estimation & context compaction engine
├── domain/       # Pure Python zero-dependency entities (Messages, Rounds)
├── dto/          # Boundary Pydantic DTO models
├── hooks/        # Tool call middleware chain & security hooks
├── loop.py       # Core agent loop
├── mcp/          # Role-scoped stdio MCP server
├── providers/    # LLM provider clients & ProviderRouter facade
└── tools/        # Tool registry, execution handlers, and dispatch
```

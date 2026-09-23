# Agent Session Execution Module Research

This document analyzes the execution layer in pelmeni against primary sources in the repository, ADRs, the domain glossary, and planned roadmap tickets.

## 1. Problem Statement and Primary Source Citations

The current execution layer splits responsibility across several disconnected modules. Callers must coordinate message history, mutable global configuration, context compaction, and tool dispatch manually.

### Primary Source Evidence

1. **Stateless loop function with mutable parameter passing**
   - Source: `src/pelmeni/loop.py:25-92`
   - `loop.run()` takes five separate arguments: `messages`, `trace`, `context`, `registry`, and `compaction_config`.
   - It directly mutates the caller's `messages` list in place (`messages[:] = compact_result.messages` at line 50; `messages.append(assistant_msg)` at line 75).
   - It holds no persistent execution state. Once `loop.run()` returns, the execution context dissolves unless the caller preserves the list.

2. **Caller coordinates orchestration and mutates global state**
   - Source: `src/pelmeni/cli/repl.py:39-69`
   - `setup_session()` configures the provider router globally via `provider.configure(agent="reviewer")` at line 41.
   - It configures tool hooks globally via `loop.tools.configure_hooks(load_hooks(...))` at line 43.
   - It hardcodes the reviewer role in `HookContext(agent_role="reviewer", session_id=trace.session_id)` at line 48.
   - It hardcodes `SYSTEM_PROMPT` as a module string at line 21.
   - `run_repl()` manually appends `UserMessage` to the list and invokes `loop.run()` on every turn.

3. **Global singleton in the provider router**
   - Source: `src/pelmeni/providers/router.py:19-131`
   - `ProviderRouter` stores a single `_provider` and `_model` on lines 32 to 33.
   - Line 100 defines `_ROUTER = ProviderRouter()`.
   - Module functions `configure()` and `chat()` delegate directly to `_ROUTER`.
   - When multiple agent types run concurrently, configuring one agent type overwrites `_ROUTER` for all other running agents.

4. **Global mutable hook chain in tool dispatch**
   - Source: `src/pelmeni/tools/dispatch.py:19-28`
   - Line 19 sets `_hook_chain: HookChain | None = None`.
   - Line 22 defines `configure_hooks(chain: HookChain)` which writes to module state.
   - Line 31 in `_run_hooks()` reads from that single module variable.
   - Concurrent agent sessions executing tool calls cannot use distinct hook chains or isolate tool security policies.

5. **Violation of ADR-0002 independent context compaction**
   - Source: `docs/adr/0002-persistent-agent-sessions.md:1-12`
   - ADR-0002 states: "All Agent Sessions accumulate Model Context pressure over the lifetime of a Session. Context compaction must be applied per Agent Session independently, not globally."
   - Because no `AgentSession` entity exists in the codebase today, compaction logic in `src/pelmeni/context/compactor.py` executes inside `loop.py` on whatever list the caller passes in. There is no encapsulated lifetime for an individual agent session's history.

6. **Roadmap conflict with Ticket #23**
   - Source: `PLAN.md:36-43`, Issue #23
   - Issue #23 requires: "Five Agent Sessions are created when the Session starts, each backed by the Agent Profile for its Agent Type... Each Agent Session runs its own agent loop connected to the Bus for receiving and sending messages."
   - Under the current structure, a multi-agent supervisor would need to instantiate five separate message lists, constantly reconfigure the global `ProviderRouter`, swap out global hook chains, and manually step the loop function.

---

## 2. Architectural Analysis: Depth, Seams, and Locality

### Shallow Module Assessment

Applying the deletion test to `loop.py`:
If `loop.py` were deleted today, its complexity would not vanish. Its complexity would move directly into `cli/repl.py` and into the future multi-agent supervisor in ticket #23. `loop.py` is shallow: its interface is five parameters wide, and its implementation only stitches together the compactor, router, and dispatch modules without owning the execution lifecycle.

### The Seam

Michael Feathers defines a seam as a place where behavior can change without editing code in that place.
In pelmeni, the execution seam sits between the message transport (REPL input queue or Bus task queue) and the internal turn evaluation pipeline (message storage, token compaction, provider execution, tool dispatch).

Today, that seam is porous:
- The caller reaches across the seam to configure providers and hooks.
- The caller reaches across the seam to manipulate raw `domain.Message` lists.
- Tool dispatch reaches across the seam into global module state.

### Locality Gains

Deepening the execution layer into an `AgentSession` module produces locality:
- **State locality**: Message history, token counts, and current round turns live inside the session instance.
- **Configuration locality**: The agent profile, model resolution, allowed tools whitelist, and hook chain are bound to the session instance, eliminating global variables.
- **Compaction locality**: Token estimation and context truncation execute within the session boundary without external triggers.
- **Fault locality**: Provider errors or tool execution failures are captured and recorded directly into the session trace.

### Leverage Gains

- **One execution interface for REPL and Bus**: The REPL and the multi-agent bus runner interact with the same session interface.
- **Clean test surface**: Tests instantiate an `AgentSession` with in-memory adapters and verify multi-turn interactions through one method call, with zero patching of module globals.

---

## 3. Structural Specification for the Deepened Module

An `AgentSession` module encapsulates the execution lifecycle defined in `CONTEXT.md`.

### Core Responsibilities Encapsulated Behind the Seam

1. **Identity and Profile**: Holds the `AgentProfile` (`manager`, `investigator`, `builder`, `reviewer`, `tester`), including its static system prompt, model alias, and tool whitelist.
2. **Context Memory**: Manages the message sequence starting from `SystemMessage`. Appends user turns, assistant responses, and tool outputs.
3. **Compaction Engine**: Evaluates token limits using `TruncateCompactor` before each LLM turn, preserving system prompts while compacting history.
4. **Provider Invocation**: Binds directly to the resolved `Provider` instance and model identifier without touching global state.
5. **Tool Execution Pipeline**: Owns the tool execution flow for this session. Enforces registry whitelisting, evaluates scoped hooks, runs handlers, and logs tool results.
6. **Turn Iteration**: Executes the loop until the model returns a final text response or hits the turn cap.

### Interaction with Adjacent Modules

- **With Agent Profile (Issue #33)**: `AgentSession` is initialized from an `AgentProfile`.
- **With Common Bus Protocol (Issue #32)**: In multi-agent mode, a worker loop listens on a bus queue, receives a `TaskPayload`, passes it to `AgentSession.step()`, and publishes the result.
- **With Session Log (Issue #34)**: `AgentSession` writes to the project session hierarchy using its `agent_type` identifier, keeping subagent traces isolated.
- **With REPL (Issues #36, #37)**: The REPL delivers the initial user prompt to the Manager `AgentSession` and awaits its response.

---

## 4. Primary Source Reference Index

| Concept / Finding | Primary Source File | Lines / Section |
| :--- | :--- | :--- |
| Agent Loop Execution | `src/pelmeni/loop.py` | lines 25–92 |
| REPL Setup & Global State Mutation | `src/pelmeni/cli/repl.py` | lines 39–69 |
| Hardcoded REPL System Prompt | `src/pelmeni/cli/repl.py` | lines 21–24 |
| Global Provider Router Singleton | `src/pelmeni/providers/router.py` | lines 19–33, 100–131 |
| Global Hook Chain State | `src/pelmeni/tools/dispatch.py` | lines 19–28, 30–43 |
| Tool Dispatch & Context Threading | `src/pelmeni/tools/dispatch.py` | lines 101–122 |
| Truncate Compactor Implementation | `src/pelmeni/context/compactor.py` | lines 60–184 |
| Domain Message Entities | `src/pelmeni/domain/messages.py` | lines 13–57 |
| Domain Round Grouping | `src/pelmeni/domain/rounds.py` | lines 12–42 |
| Trace File Writer | `src/pelmeni/trace.py` | lines 18–42 |
| Agent Type & Agent Session Glossary | `CONTEXT.md` | lines 7–42 |
| Turn, Round & Model Context Glossary | `CONTEXT.md` | lines 105–123 |
| Persistent Agent Sessions Decision | `docs/adr/0002-persistent-agent-sessions.md` | lines 1–12 |
| Tool Access Enforced by Registry | `docs/adr/0005-registry-enforced-tool-access.md` | lines 1–12 |
| Fail-Closed Hooks Decision | `docs/adr/0006-fail-closed-hooks.md` | lines 1–12 |
| Multi-agent Session Lifecycle Spec | `PLAN.md` (Issue #23) | lines 36–43 |
| Agent Profiles & Prompts Spec | `PLAN.md` (Issue #33) | lines 13–15 |
| Session Hierarchy & Trace Spec | `PLAN.md` (Issue #34) | lines 16–18 |
| Common Bus Protocol Spec | `PLAN.md` (Issue #32) | lines 10–12 |

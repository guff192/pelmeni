# Session Storage and Hierarchy Module Research

This document analyzes the session storage and trace logging layer in pelmeni against primary sources in the repository, domain terminology, ADRs, and roadmap tickets #34, #35, and #37.

## 1. Problem Statement and Primary Source Citations

The current session logging implementation is a shallow file-appender class. It lacks directory hierarchy management, structured line-1 header storage, subagent log isolation, and replay parsing capabilities.

### Primary Source Evidence

1. **Shallow class with append-only write loop**
   - Source: `src/pelmeni/trace.py:18-42`
   - `Trace` contains only one public method: `log(event: str, trace_data: dict) -> None`.
   - On line 41, `log()` executes `with self.trace_file.open("a", encoding="utf-8") as trace_file: trace_file.write(f"{line}\n")`.
   - The class opens, appends, and closes the file descriptor on every event.
   - It performs zero validation or schema enforcement on `trace_data`.

2. **Zero test coverage for session tracing**
   - Source: `tests/`
   - A search for `Trace` instantiations across `tests/` yields zero occurrences.
   - All tests interacting with the loop mock trace logging: `trace = MagicMock()` (`tests/test_context_engine.py:1-25`, `tests/test_tool_interfaces.py:1-20`).
   - The filesystem creation, path hashing, and file writes in `Trace` are completely untested.

3. **Flat directory layout and missing timestamp ordering**
   - Source: `src/pelmeni/trace.py:21-27`
   - Line 23 generates `session_id = sha256(f"{time.time()}-{uuid.uuid4()}".encode()).hexdigest()[:8]`.
   - Line 26 sets `self.dir = SESSIONS_ROOT / project / session_id`.
   - Directories on disk lack timestamp prefixes (`~/.pelmeni/sessions/<project>/<session-id>/`).
   - Determining the latest session for continuation requires inspecting filesystem stat modification times across every directory.
   - Issue #34 requires a structured hierarchy: `~/.pelmeni/sessions/<project>/<timestamp>_<slug>_<hash>/`.

4. **Missing line-1 session header metadata**
   - Source: `src/pelmeni/trace.py:35-42`, `PLAN.md:16-18` (Issue #34), `PLAN.md:26-28` (Issue #35)
   - `Trace` writes no metadata header record. The first line of `trace.jsonl` is whatever event happens first (e.g. `context_compacted` or `request`).
   - Issue #34 requires a fast line-1 `session_header` record for instant metadata discovery.
   - Issue #35 requires persisting the remote bridge `conversation_id` inside this header to preserve TPU prefix caches across turns.

5. **No subagent trace isolation**
   - Source: `src/pelmeni/trace.py:28`, `PLAN.md:16-18` (Issue #34)
   - All events from all agents write into a single file: `self.trace_file = self.dir / "trace.jsonl"`.
   - When workers or subagents run, their tool invocations and model requests interleave directly with user REPL turns.
   - Issue #34 specifies an isolated subdirectory: `<session_dir>/subagents/<agent_type>_<timestamp>_<short_id>.jsonl`.

6. **Missing read and deserialization capabilities**
   - Source: `src/pelmeni/trace.py:18-42`, `PLAN.md:29-32` (Issue #37)
   - `Trace` provides no methods to read, query, or deserialize stored sessions.
   - Issue #37 requires resuming sessions via `pelmeni --continue` and `pelmeni --resume <session_id>`.
   - Without read methods in the storage module, callers in the CLI would have to parse JSONL files and reconstruct domain message objects manually.

7. **Domain terminology divergence**
   - Source: `CONTEXT.md:97-99`
   - `CONTEXT.md` explicitly defines:
     `Session Log: The JSONL trace file recording every request, response, and tool event that occurred during a Session. Avoid: trace, log file, session trace.`
   - The current code uses the forbidden terms `Trace`, `trace.py`, and `trace.jsonl`.

---

## 2. Architectural Analysis: Depth, Seams, and Locality

### Shallow Module Assessment

Applying the deletion test to `src/pelmeni/trace.py`:
Deleting `Trace` today would merely move a single `open("a")` call into `cli/repl.py`. The class has virtually no implementation hiding behind its interface. It is a shallow pass-through to Python file writing.

### The Seam

The storage seam sits between session runtime actors (REPL, Supervisor, Agent Sessions, Provider bridges) and the persistent disk layout.

Today, this seam is incomplete:
- Callers like `cli/repl.py` directly pass `Path.cwd()` to `Trace`.
- Callers pass `trace.session_id` to configure `HookContext`.
- Provider bridges (`src/pelmeni/providers/antigravity/process.py:21-40`) synthesize isolated temporary home paths separately.
- There is no seam for reading historical session traces.

### Locality Gains

Deepening this layer into a `SessionStore` module produces strong locality:
- **Filesystem locality**: Directory naming conventions, timestamp formatting, slug generation, and hash derivation live in one place.
- **Header locality**: Session metadata, model configuration, and bridge conversation identifiers are read and written through typed header operations.
- **Trace isolation locality**: Subagent trace log file naming and directory creation stay internal to the store module.
- **Reconstruction locality**: Deserializing JSON lines into pure domain `Message` and `Round` entities lives inside the store reader, keeping the REPL clean.

### Leverage Gains

- **Multiple callers share one storage interface**:
  1. Interactive REPL logs turns and reads history.
  2. Provider bridges read and update `conversation_id` for TPU prefix cache hits.
  3. Resumption commands (`--continue`, `--resume`) reload past sessions without ad-hoc parsers.
  4. Multi-agent sessions spawn isolated subagent trace files.
- **Test surface**: Tests instantiate an in-memory or temp-directory `SessionStore` and verify session lifecycle, subagent logging, and round reconstruction through a unified interface.

---

## 3. Structural Specification for the Deepened Module

The `SessionStore` module manages disk persistence and history recovery.

### Storage Interface

1. **`SessionStore.create(workspace: Path) -> SessionStore`**
   - Computes project slug, timestamp, and unique hash: `~/.pelmeni/sessions/<project>/<timestamp>_<slug>_<hash>/`.
   - Creates the session directory and the `subagents/` subdirectory.
   - Initializes `main.jsonl`.

2. **`SessionStore.open(session_dir: Path) -> SessionStore`**
   - Opens an existing session directory for inspection or continuation.

3. **`write_header(header: SessionHeader) -> None`**
   - Writes the line-1 header record to `main.jsonl`.
   - Stores workspace path, start timestamp, active agent profile, and optional bridge `conversation_id`.

4. **`read_header() -> SessionHeader`**
   - Reads line 1 of `main.jsonl` and returns a typed `SessionHeader`.
   - O(1) execution without scanning the remainder of the file.

5. **`update_bridge_conversation_id(conversation_id: str) -> None`**
   - Atomically updates or records the remote bridge identifier in session metadata for cache preservation.

6. **`log_event(event: str, data: dict, agent_type: str | None = None) -> None`**
   - Appends a structured event line to `main.jsonl`.
   - Tags events with `ts` and `agent_type`.

7. **`create_subagent_log(agent_type: str) -> SubagentLogger`**
   - Spawns a dedicated file: `subagents/<agent_type>_<timestamp>_<short_id>.jsonl`.
   - Returns a scoped logger for subagent turns, isolating subagent traces from `main.jsonl`.

8. **`read_history() -> list[Message]` and `read_rounds() -> list[Round]`**
   - Parses `main.jsonl` into domain messages and groups them into `Round` objects.
   - Reconstructs context for session resumption.

9. **`find_latest(workspace: Path) -> Path | None`**
   - Scans project session folders using timestamp prefixes to identify the most recent session instantly.

---

## 4. Primary Source Reference Index

| Concept / Requirement | Primary Source File | Lines / Section |
| :--- | :--- | :--- |
| Current Trace Writer Implementation | `src/pelmeni/trace.py` | lines 18–42 |
| File Open on Every Log Turn | `src/pelmeni/trace.py` | lines 41–42 |
| SHA-256 Session ID Generation | `src/pelmeni/trace.py` | lines 23–25 |
| REPL Trace Instantiation | `src/pelmeni/cli/repl.py` | lines 44–48 |
| Context Engine Trace Mocking | `tests/test_context_engine.py` | lines 1–25 |
| Tool Interface Trace Mocking | `tests/test_tool_interfaces.py` | lines 1–20 |
| DTO TraceEvent Model | `src/pelmeni/dto/trace.py` | lines 8–14 |
| Session Log Terminology | `CONTEXT.md` | lines 97–99 |
| Session Directory Layout & Subagent Spec | `PLAN.md` (Issue #34) | lines 16–18 |
| Bridge Conversation ID Continuity Spec | `PLAN.md` (Issue #35) | lines 26–28 |
| REPL Session Resumption Spec | `PLAN.md` (Issue #37) | lines 29–32 |
| Shared Session Log Multi-Agent Requirement | `PLAN.md` (Issue #23) | lines 41–43 |

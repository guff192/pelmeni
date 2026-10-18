# ADR 0011: Terminal REPL Rendering Engine (Rich vs Textual)

## Context

Issue #48 evaluated UI rendering architectures for Pelmeni's interactive REPL (`src/pelmeni/cli/repl.py`) inside tmux environments, satisfying requirements laid out in `docs/spec-repl-tui-enhancements.md`.

We constructed and evaluated two working prototypes:
1. `src/pelmeni/cli/spike_rich.py`: Inline streaming, live line replacement (`rich.live.Live`), and markdown formatting using `rich`.
2. `src/pelmeni/cli/spike_textual.py`: Full-screen TUI application layout, collapsible containers, loading spinners, and markdown widgets using `textual`.

## Evaluation Criteria & Findings

| Evaluation Metric | `rich` (Inline stdout stream) | `textual` (Full-screen App) |
| :--- | :--- | :--- |
| **Natural tmux scrolling** | **Native**: Writes directly to primary stdout; standard tmux scrollback (`Prefix + [`, mouse wheel) works seamlessly across past sessions. | **Intercepted**: Operates in alternate screen buffer (`smcup`/`rmcup`). Mouse wheel scrolling is captured by internal widget containers, not tmux scrollback. |
| **Native Clipboard / Copy-Mode** | **Native**: Terminal emulator selection and tmux selection work across the entire conversation history without interference. | **Restricted**: Terminal mouse selection requires holding `Shift` or disabling mouse capture. Screen clears on exit (`rmcup`), removing visual history. |
| **Prompt Box & `prompt_toolkit` Integration** | **Seamless**: `prompt_toolkit.PromptSession` coexists cleanly with inline stdout output. Frame toggles (`~is_done`) preserve scrollback. | **Conflicted**: Textual takes over the full terminal display lifecycle, requiring re-implementing prompt inputs or embedding complex widget layers. |
| **Live In-Place Line Updates** | **Supported**: `rich.live.Live` / cursor repositioning cleanly updates transient states (in-flight tool execution, streaming thinking spinner) and leaves completed output committed to terminal scrollback. | **Supported**: Widget reactivity cleanly re-renders DOM nodes in real-time. |
| **Complexity & Overhead** | **Minimal**: Lightweight library (~15 MB installed with deps), synchronous/async friendly, zero event-loop hijacking. | **High**: Heavy asynchronous framework requiring its own application event loop, CSS layout engine, and full widget lifecycle management. |

## Decision

We select **`rich`** as the rendering engine for Pelmeni's terminal REPL.

1. **Inline terminal philosophy**: Pelmeni is designed as an agent harness for developer workflows inside terminal multiplexers (tmux). The primary interface must remain an inline streaming REPL where terminal history persists naturally in the emulator's scrollback buffer.
2. **`prompt_toolkit` synergy**: Pelmeni's REPL already relies on `prompt_toolkit` for multiline input, keybindings (`Shift+Enter`, `Ctrl+T`), and history. `rich` integrates natively without fighting for terminal control or alternate screen management.
3. **Ergonomic alignment with Spec #47**: Thinking blocks and tool summaries will be rendered inline with ANSI styling and `rich.live.Live` in-place transitions, committing finalized outputs directly to terminal scrollback.

## Consequences

- Keep `rich` in project dependencies (`pyproject.toml`).
- Remove `textual` from project dependencies to keep the dependency footprint small and eliminate unused packages.
- Implement thinking block toggles and tool summaries in `src/pelmeni/cli/repl.py` using `rich.console.Console`, `rich.markdown.Markdown`, and `rich.live.Live`.

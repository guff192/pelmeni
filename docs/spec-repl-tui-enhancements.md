# Spec: Terminal REPL UX Enhancements (Prompt Box, Thinking Stream, Tool Summaries & Pager)

## Problem Statement

The interactive REPL currently prints unformatted plain text directly to standard output. When agent models produce extended reasoning (Thinking Blocks), large volumes of unstyled text scroll through the terminal, obscuring the boundary between internal reasoning and final answers. When tools run, there is no real-time indication that an external command is active, and once executed, verbose tool outputs (such as test suites or file listings) flood the terminal history with hundreds of lines. Additionally, the multiline prompt lacks visual boundaries and dynamic role metadata, making it difficult to discern where the user's input ends and agent responses begin.

## Solution

Deliver an advanced terminal presentation layer that preserves natural tmux and terminal scrolling while introducing structured visual ergonomics:

1. **Framed Prompt Box**: A transient input container with borders and a top title displaying the active Agent Type and model (`┌─ [Reviewer: Sonnet] ─────────────┐`), rendered conditionally so the frame disappears upon submission and leaves clean prompt text in scrollback.
2. **Thinking Block with Live Stream Toggle**: Dimmed grey rendering for model reasoning during active streaming, with `Ctrl+T` toggling visibility mid-stream via in-place ANSI cursor control to collapse into a single-line status indicator. When reasoning finishes, the block is permanently committed to standard output.
3. **Two-Stage Tool Summary Lifecycle**: An immediate in-flight status indicator (`▶ tool: command [running...]`) that updates in-place upon completion into a compact status record (`✓ tool (duration, exit code)`) showing head and tail output snippets with elided middles.
4. **Interactive Tool Inspector**: A `/inspect` REPL command providing an interactive selector to choose any tool invocation from the current Round and view its complete, un-truncated stdout and stderr in `$PAGER`.
5. **Renderer Architecture Evaluation**: A prototype phase comparing inline `rich` formatting against a `textual` application architecture before locking the terminal rendering engine.

## User Stories

1. As a developer using tmux, I want the terminal to scroll naturally, so that standard tmux copy-mode, mouse wheel scrolling, and pane splits operate without interference.
2. As a user entering a multiline prompt, I want the input buffer enclosed in a bordered Prompt Box with the active Agent Type and model in the top border, so that I can see the input boundaries and active context at a glance.
3. As a user submitting a prompt, I want the Prompt Box frame to disappear on Enter (`show_frame=~is_done`), so that terminal history only retains the clean prompt text without redundant box borders.
4. As a user observing agent reasoning, I want the Thinking Block rendered in muted grey text, so that internal model deliberation is visually separated from final answers and tool results.
5. As a user reading an assistant reply, I want markdown rendered with syntax-highlighted code fences and formatted headers, so that explanations and code are legible.
6. As a user during active model reasoning, I want to press `Ctrl+T` to collapse the streaming Thinking Block into a single-line indicator, so that long reasoning streams do not push earlier context off-screen.
7. As a user after model reasoning finishes, I want the Thinking Block to remain committed to scrollback as is, so that terminal history remains stable and copyable.
8. As a user when a tool starts executing, I want an immediate in-flight status indicator (`▶ <tool>: <command> [running...]`), so that I have real-time confirmation that work is in progress.
9. As a user when a tool finishes executing, I want the in-flight indicator replaced in-place by a compact Tool Summary showing execution duration, exit status, and head/tail output snippets, so that lengthy outputs do not overwhelm terminal scrollback.
10. As a user encountering tool failures or complex outputs, I want to run `/inspect` in the REPL, so that I can inspect the full raw output without cluttering the main conversation view.
11. As a user running `/inspect`, I want an interactive arrow-key picker listing all tool calls from the current Round, so that I can easily select the specific execution I want to audit.
12. As a user selecting a tool call in `/inspect`, I want the complete output opened in `$PAGER` (defaulting to `less -R`), so that I can navigate, search, and paginate through full logs.
13. As a user closing `$PAGER`, I want to return immediately to the REPL prompt, so that my interactive workflow continues seamlessly without lost state.
14. As an engineer evaluating UI libraries, I want a prototype comparing `rich` inline rendering against `textual` application layout, so that the team can make an informed decision on UI architecture.

## Implementation Decisions

- **Transient Prompt Box**: Implemented using `prompt_toolkit.layout.containers.Frame` wrapping the input buffer control, conditioned with `show_frame=~is_done`. The frame header dynamically formats the current `AgentType` and active model alias.
- **In-Place Live Stream Updates**: Live thinking text and in-flight tool indicators use ANSI cursor positioning (`\x1b[A`, `\x1b[K`) or `rich.live.Live` to update active lines in-place without generating separate scrolling entries.
- **Thinking Block State Machine**:
  - `STREAMING_EXPANDED`: Emits grey text to terminal; listens for `Ctrl+T`.
  - `STREAMING_COLLAPSED`: Erases stream lines and renders single-line spinner; listens for `Ctrl+T`.
  - `COMMITTED`: Reached when reasoning ends; stream is locked into standard stdout.
- **Two-Stage Tool Summary**: Tool dispatch notifies the renderer prior to execution (`on_tool_start`) to print the in-flight status line. Upon return (`on_tool_complete`), the renderer overwrites the in-flight line with the compact summary containing execution duration, exit code, and elided output.
- **Tool Output Buffer & Pager Invocation**: Full raw stdout, stderr, and arguments of every tool call in a Round are retained in an in-memory session buffer. The `/inspect` command uses a `prompt_toolkit` menu or dialog to select a tool invocation, writes the full content to a temporary descriptor, and invokes `$PAGER` via standard subprocess mechanics before resuming the REPL.
- **Prototype Evaluation Gate**: A standalone prototype will evaluate `rich` (inline scrolling) versus `textual` (screen-based application) inside a tmux environment before locking the rendering library.

## Testing Decisions

- **Primary Seam**: The REPL Terminal Renderer interface. Rather than asserting on physical terminal visual output, tests drive the renderer with synthetic event streams (tool start, tool chunk, tool finish, thinking token, keypress) and assert on emitted ANSI codes, state transitions, and pager parameters.
- **Input Seam**: Use `prompt_toolkit.input.create_pipe_input` and `DummyOutput` (following the pattern established in `tests/test_repl.py`) to verify keybindings (`Ctrl+T`), frame toggling (`~is_done`), and slash-command routing.
- **Inspection Seam**: Test `/inspect` by mocking `$PAGER` invocation and verifying that the exact raw tool output buffer is passed to the pager.
- **Prior Art**: `tests/test_repl.py` for pipe input testing; `tests/test_session.py` for session state and history.

## Out of Scope

- Full graphical web or desktop user interface.
- Modifying non-interactive MCP stdio server outputs.
- Mouse-driven text manipulation outside standard terminal emulator capabilities.
- Live background process management independent of the current agent turn.

## Further Notes

- Builds on the prompt_toolkit REPL overhaul completed in issue #36.
- Aligns with domain glossary terms defined in `CONTEXT.md`: `Prompt Box`, `Thinking Block`, and `Tool Summary`.

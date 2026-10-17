# flake8: noqa: WPS201
"""Interactive REPL session handling using prompt_toolkit."""

from __future__ import annotations

import dataclasses
import enum
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import is_searching
from prompt_toolkit.history import FileHistory, History
from prompt_toolkit.input.vt100_parser import ANSI_SEQUENCES
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.shortcuts import PromptSession

from pelmeni import loop
from pelmeni.config import ConfigService
from pelmeni.context.compactor import get_default_compactor
from pelmeni.domain.agent_types import AgentType
from pelmeni.domain.messages import SystemMessage, UserMessage
from pelmeni.dto.context import CompactionConfigSchema
from pelmeni.dto.hooks import HookContext
from pelmeni.dto.tools import AgentRole
from pelmeni.hooks.loader import load_hooks
from pelmeni.providers import router as provider
from pelmeni.session import SessionStore

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document
    from prompt_toolkit.input import Input
    from prompt_toolkit.output import Output

    from pelmeni.domain.messages import Message

SYSTEM_PROMPT = (
    "You are a pelmeni agent: a helpful coding assistant with a bash tool. "
    "Prefer running commands to gather facts over guessing. Be concise."
)

DEFAULT_HISTORY_FILE = Path.home() / ".pelmeni" / "history"

SLASH_COMMANDS: dict[str, str] = {
    "/task": "Execute a development task prompt",
    "/role": "Inspect or switch active agent role",
    "/model": "Inspect current provider model",
    "/compact": "Compact session message context",
    "/clear": "Clear the terminal screen",
    "/trace": "Display session log file path",
    "/help": "Show available commands and keybindings",
    "/exit": "Exit the interactive session",
}

KEY_KITTY_SHIFT_ENTER = "\x1b[13;2u"
KEY_XTERM_SHIFT_ENTER = "\x1b[27;2;13~"
SCREEN_CLEAR_SEQUENCE = "\x1b[2J\x1b[H"


class CommandOutcome(enum.Enum):
    """Outcome returned after evaluating a REPL slash command."""

    HANDLED = "handled"
    RUN_PROMPT = "run_prompt"
    EXIT = "exit"


@dataclasses.dataclass(frozen=True)
class SlashCommandResult:
    """Result of evaluating a slash command."""

    outcome: CommandOutcome
    prompt: str | None = None
    context: HookContext | None = None

    def __iter__(self) -> Iterator[Any]:
        """Allow unpacking as (outcome, prompt)."""
        return iter((self.outcome, self.prompt))


class SlashCommandCompleter(Completer):
    """Auto-completer for REPL slash commands with description previews."""

    def __init__(self, commands: dict[str, str] | None = None) -> None:
        """Initialize slash command completer with optional command catalog."""
        self._commands = commands or SLASH_COMMANDS

    def get_completions(
        self,
        document: Document,
        _complete_event: CompleteEvent | None,
    ) -> Iterable[Completion]:
        """Yield slash command completions matching text before cursor."""
        word = document.get_word_before_cursor(WORD=True)
        if not word.startswith("/"):
            return
        for cmd, desc in self._commands.items():
            if cmd.startswith(word):
                yield Completion(
                    text=cmd,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=desc,
                )


def register_terminal_key_sequences() -> None:
    """Register terminal escape sequences for Shift+Enter."""
    ANSI_SEQUENCES[KEY_KITTY_SHIFT_ENTER] = Keys.ControlJ
    ANSI_SEQUENCES[KEY_XTERM_SHIFT_ENTER] = Keys.ControlJ


def create_repl_key_bindings() -> KeyBindings:
    """Build keybindings supporting multiline Shift+Enter and submit Enter."""
    bindings = KeyBindings()

    @bindings.add("c-m", filter=~is_searching)
    def _handle_enter(event: KeyPressEvent) -> None:
        buff = event.current_buffer
        if buff.complete_state and buff.complete_state.current_completion:
            buff.apply_completion(buff.complete_state.current_completion)
        else:
            buff.validate_and_handle()

    @bindings.add("c-j")
    def _handle_shift_enter(event: KeyPressEvent) -> None:
        event.current_buffer.insert_text("\n")

    @bindings.add("escape", "c-m")
    def _handle_alt_enter(event: KeyPressEvent) -> None:
        event.current_buffer.insert_text("\n")

    return bindings


def get_history_file(path: Path | None = None) -> Path:
    """Resolve history file location and ensure its parent directory exists."""
    target = path or DEFAULT_HISTORY_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def create_prompt_session(
    history: History | None = None,
    history_file: Path | None = None,
    input: Input | None = None,  # noqa: A002
    output: Output | None = None,
) -> PromptSession[str]:
    """Create a configured prompt_toolkit PromptSession."""
    register_terminal_key_sequences()
    effective_history = history or FileHistory(
        str(get_history_file(history_file))
    )
    return PromptSession[str](
        history=effective_history,
        key_bindings=create_repl_key_bindings(),
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        editing_mode=EditingMode.EMACS,
        multiline=True,
        input=input,
        output=output,
    )


def _handle_help_command() -> SlashCommandResult:
    """Print help overview with command explanations and keybindings."""
    print("\nPelmeni REPL Commands:")
    for cmd, desc in sorted(SLASH_COMMANDS.items()):
        print(f"  {cmd:<10} {desc}")
    print("\nKeybindings:")
    print("  Enter         Submit prompt")
    print("  Shift+Enter   Insert newline (multiline)")
    print("  Alt+Enter     Insert newline (fallback)")
    print("  Ctrl+A / E    Jump to beginning / end of line")
    print("  Ctrl+R        Reverse history search")
    print("  Ctrl+D        Exit session (on empty line)")
    print("  Ctrl+C        Cancel current line")
    return SlashCommandResult(outcome=CommandOutcome.HANDLED)


def _handle_role_command(
    arg: str, context: HookContext | None
) -> SlashCommandResult:
    """Inspect or update the active agent role."""
    if not arg:
        current_role = context.agent_role if context else "unspecified"
        print(f"active role: {current_role}")
        return SlashCommandResult(outcome=CommandOutcome.HANDLED)

    valid_roles = {role.value for role in AgentRole}
    target_role = arg.lower()
    if target_role not in valid_roles:
        choices = ", ".join(sorted(valid_roles))
        print(f"invalid role '{arg}'. Choose from: {choices}")
        return SlashCommandResult(outcome=CommandOutcome.HANDLED)

    updated_context = None
    if context is not None:
        updated_context = dataclasses.replace(context, agent_role=target_role)
    provider.configure(agent=target_role)
    print(f"switched active role to: {target_role}")
    return SlashCommandResult(
        outcome=CommandOutcome.HANDLED, context=updated_context
    )


def _handle_compact_command(messages: list[Message]) -> SlashCommandResult:
    """Compact message history using default compactor."""
    compactor = get_default_compactor()
    schema = CompactionConfigSchema(enabled=True)
    result = compactor.compact(messages, schema)
    messages.clear()
    messages.extend(result.messages)
    print(
        f"context compacted: {result.tokens_before} -> "
        f"{result.tokens_after} tokens "
        f"({result.original_count} -> {result.compacted_count} messages)"
    )
    return SlashCommandResult(outcome=CommandOutcome.HANDLED)


def _handle_task_command(arg: str) -> SlashCommandResult:
    """Evaluate task prompt submission."""
    if not arg:
        print("Usage: /task <prompt text>")
        return SlashCommandResult(outcome=CommandOutcome.HANDLED)
    return SlashCommandResult(outcome=CommandOutcome.RUN_PROMPT, prompt=arg)


def _dispatch_state_command(
    command: str,
    arg: str,
    messages: list[Message],
    context: HookContext | None,
) -> SlashCommandResult:
    """Dispatch stateful slash commands modifying session or context."""
    if command == "/role":
        return _handle_role_command(arg, context)
    if command == "/compact":
        return _handle_compact_command(messages)
    if command == "/task":
        return _handle_task_command(arg)

    print(f"Unknown command: {command}. Type /help for available commands.")
    return SlashCommandResult(outcome=CommandOutcome.HANDLED)


def handle_slash_command(
    line: str,
    messages: list[Message],
    trace: SessionStore | None,
    context: HookContext | None,
) -> SlashCommandResult:
    """Dispatch and evaluate a slash command line."""
    parts = line.strip().split(maxsplit=1)
    command = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/exit":
        return SlashCommandResult(outcome=CommandOutcome.EXIT)
    if command == "/help":
        return _handle_help_command()
    if command == "/clear":
        print(SCREEN_CLEAR_SEQUENCE, end="", flush=True)
        return SlashCommandResult(outcome=CommandOutcome.HANDLED)
    if command == "/trace":
        log_file = trace.main_log_file if trace else "none"
        print(f"session log: {log_file}")
        return SlashCommandResult(outcome=CommandOutcome.HANDLED)
    if command == "/model":
        print(f"configured model: {provider.describe()}")
        return SlashCommandResult(outcome=CommandOutcome.HANDLED)

    return _dispatch_state_command(command, arg, messages, context)


def read_input(
    prompt_session: PromptSession[str] | None = None,
) -> str | None:
    """Read one user input line; None ends session, empty string skips turn."""
    session = prompt_session or create_prompt_session()
    try:
        line = session.prompt("\n> ").strip()
    except EOFError, KeyboardInterrupt:
        print()
        return None
    if line == "/exit":
        return None
    return line


def setup_session() -> tuple[list[Message], SessionStore, HookContext]:
    """Configure providers and hooks, then create session state."""
    provider.configure(agent="reviewer")
    app_config = ConfigService().load()
    loop.tools.configure_hooks(load_hooks(app_config, app_config.raw_hooks))
    store = SessionStore.create(Path.cwd())
    store.ensure_header(initial_agent=AgentType.REVIEWER)
    return (
        [SystemMessage(content=SYSTEM_PROMPT)],
        store,
        HookContext(agent_role="reviewer", session_id=store.session_id),
    )


def run_repl(
    messages: list[Message],
    trace: SessionStore,
    context: HookContext,
    prompt_session: PromptSession[str] | None = None,
) -> None:
    """Run the interactive REPL loop with prompt_toolkit ergonomics."""
    session = prompt_session or create_prompt_session()
    active_context = context
    while True:
        try:
            line = session.prompt("\n> ").strip()
        except EOFError, KeyboardInterrupt:
            print()
            break

        if not line:
            continue

        if line.startswith("/"):
            result = handle_slash_command(line, messages, trace, active_context)
            if result.context is not None:
                active_context = result.context
            if result.outcome == CommandOutcome.EXIT:
                break
            if result.outcome == CommandOutcome.HANDLED:
                continue
            if result.outcome == CommandOutcome.RUN_PROMPT and result.prompt:
                line = result.prompt

        messages.append(UserMessage(content=line))
        answer = loop.run(messages, trace, active_context)
        if answer:
            print(f"\n{answer}")
        else:
            print("\n(no answer; see stderr and trace)", file=sys.stderr)

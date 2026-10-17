"""Tests for interactive REPL UX overhaul with prompt_toolkit."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from prompt_toolkit.document import Document
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.formatted_text import to_plain_text
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from pelmeni.cli.repl import (
    DEFAULT_HISTORY_FILE,
    SLASH_COMMANDS,
    CommandOutcome,
    SlashCommandCompleter,
    create_prompt_session,
    create_repl_key_bindings,
    get_history_file,
    handle_slash_command,
    register_terminal_key_sequences,
    run_repl,
)
from pelmeni.domain.messages import Message, SystemMessage, UserMessage
from pelmeni.dto.hooks import HookContext
from pelmeni.session import SessionStore

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_slash_commands_catalog() -> None:
    """All required slash commands are defined in the catalog."""
    expected = {
        "/task",
        "/role",
        "/model",
        "/compact",
        "/clear",
        "/trace",
        "/help",
        "/exit",
    }
    assert expected.issubset(SLASH_COMMANDS.keys())
    for cmd in expected:
        assert isinstance(SLASH_COMMANDS[cmd], str)
        assert len(SLASH_COMMANDS[cmd]) > 0


def test_completer_all_slash_commands() -> None:
    """Completer returns all slash commands and their description previews."""
    completer = SlashCommandCompleter()
    doc = Document("/", cursor_position=1)
    completions = list(completer.get_completions(doc, None))

    completed_texts = {c.text for c in completions}
    assert completed_texts == set(SLASH_COMMANDS.keys())

    for comp in completions:
        assert comp.display_meta is not None
        assert to_plain_text(comp.display_meta) == SLASH_COMMANDS[comp.text]


def test_completer_prefix_filtering() -> None:
    """Completer filters commands by typed prefix."""
    completer = SlashCommandCompleter()

    # /t matches /task and /trace
    doc_t = Document("/t", cursor_position=2)
    comps_t = {c.text for c in completer.get_completions(doc_t, None)}
    assert comps_t == {"/task", "/trace"}

    # /ex matches /exit
    doc_ex = Document("/ex", cursor_position=3)
    comps_ex = {c.text for c in completer.get_completions(doc_ex, None)}
    assert comps_ex == {"/exit"}

    # Non-slash text should return no completions
    doc_plain = Document("hello world", cursor_position=11)
    comps_plain = list(completer.get_completions(doc_plain, None))
    assert comps_plain == []


def test_history_file_resolution(tmp_path: Path) -> None:
    """History file path creates parent directory and defaults properly."""
    custom_path = tmp_path / "custom_dir" / "history"
    resolved = get_history_file(custom_path)
    assert resolved == custom_path
    assert resolved.parent.is_dir()

    # Default history path under ~/.pelmeni/history
    default_resolved = get_history_file()
    assert default_resolved == DEFAULT_HISTORY_FILE
    assert default_resolved.parent.is_dir()


def test_history_persistence_across_sessions(tmp_path: Path) -> None:
    """Command history persists to disk and reloads in new sessions."""
    hist_file = tmp_path / "history"

    hist1 = FileHistory(str(hist_file))
    hist1.append_string("first prompt")
    hist1.append_string("second prompt")

    hist2 = FileHistory(str(hist_file))
    loaded = list(hist2.load_history_strings())
    assert "first prompt" in loaded
    assert "second prompt" in loaded


def test_create_prompt_session_configuration(tmp_path: Path) -> None:
    """PromptSession initializes with Emacs mode, history, and multiline."""
    hist_file = tmp_path / "history"
    session = create_prompt_session(history_file=hist_file)

    assert session.editing_mode == EditingMode.EMACS
    assert session.multiline is True
    assert isinstance(session.completer, SlashCommandCompleter)
    assert isinstance(session.history, FileHistory)


def test_keybinding_enter_executes() -> None:
    """Pressing Enter validates and submits the prompt."""
    register_terminal_key_sequences()
    kb = create_repl_key_bindings()
    assert kb is not None

    with create_pipe_input() as pipe_input:
        session = create_prompt_session(
            history=InMemoryHistory(),
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_text("hello prompt\r")
        result = session.prompt("> ")
        assert result == "hello prompt"


def test_keybinding_shift_enter_multiline() -> None:
    """Shift+Enter inserts a newline while Enter executes."""
    register_terminal_key_sequences()

    with create_pipe_input() as pipe_input:
        session = create_prompt_session(
            history=InMemoryHistory(),
            input=pipe_input,
            output=DummyOutput(),
        )
        # \x1b[13;2u is kitty Shift+Enter
        pipe_input.send_text("line1\x1b[13;2uline2\r")
        result = session.prompt("> ")
        assert result == "line1\nline2"


def test_keybinding_xterm_shift_enter_multiline() -> None:
    """Xterm modifyOtherKeys Shift+Enter inserts a newline."""
    register_terminal_key_sequences()

    with create_pipe_input() as pipe_input:
        session = create_prompt_session(
            history=InMemoryHistory(),
            input=pipe_input,
            output=DummyOutput(),
        )
        # \x1b[27;2;13~ is xterm Shift+Enter
        pipe_input.send_text("first\x1b[27;2;13~second\r")
        result = session.prompt("> ")
        assert result == "first\nsecond"


def test_keybinding_reverse_history_search() -> None:
    """Ctrl+R triggers reverse search across historical entries."""
    history = InMemoryHistory()
    history.append_string("echo ancient entry")
    history.append_string("echo recent entry")

    with create_pipe_input() as pipe_input:
        session = create_prompt_session(
            history=history,
            input=pipe_input,
            output=DummyOutput(),
        )
        # Ctrl+R (\x12), type 'ancient', Enter to select, Enter to execute
        pipe_input.send_text("\x12ancient\r\r")
        result = session.prompt("> ")
        assert result == "echo ancient entry"


def test_handle_slash_command_exit() -> None:
    """Command /exit returns EXIT outcome."""
    outcome, prompt = handle_slash_command("/exit", [], None, None)
    assert outcome == CommandOutcome.EXIT
    assert prompt is None


def test_handle_slash_command_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Command /help outputs description of commands and keybindings."""
    outcome, prompt = handle_slash_command("/help", [], None, None)
    assert outcome == CommandOutcome.HANDLED
    assert prompt is None
    captured = capsys.readouterr().out
    assert "/task" in captured
    assert "/exit" in captured
    assert "Shift+Enter" in captured


def test_handle_slash_command_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Command /trace displays current session log path."""
    store = SessionStore.create(tmp_path, sessions_root=tmp_path / "sessions")
    outcome, prompt = handle_slash_command("/trace", [], store, None)
    assert outcome == CommandOutcome.HANDLED
    assert prompt is None
    captured = capsys.readouterr().out
    assert str(store.main_log_file) in captured


def test_handle_slash_command_clear(capsys: pytest.CaptureFixture[str]) -> None:
    """Command /clear sends screen clear escape sequence."""
    outcome, prompt = handle_slash_command("/clear", [], None, None)
    assert outcome == CommandOutcome.HANDLED
    assert prompt is None
    captured = capsys.readouterr().out
    assert "\x1b[2J\x1b[H" in captured


def test_handle_slash_command_role(capsys: pytest.CaptureFixture[str]) -> None:
    """Command /role inspects and switches active agent role."""
    context = HookContext(agent_role="reviewer", session_id="s1")

    # Inspect current role
    outcome, _ = handle_slash_command("/role", [], None, context)
    assert outcome == CommandOutcome.HANDLED
    assert "reviewer" in capsys.readouterr().out

    # Switch to investigator
    with patch("pelmeni.providers.router.configure") as mock_cfg:
        result = handle_slash_command("/role investigator", [], None, context)
        assert result.outcome == CommandOutcome.HANDLED
        assert result.context is not None
        assert result.context.agent_role == "investigator"
        mock_cfg.assert_called_once_with(agent="investigator")
        assert "investigator" in capsys.readouterr().out


def test_handle_slash_command_model(capsys: pytest.CaptureFixture[str]) -> None:
    """Command /model displays configured model description."""
    with patch(
        "pelmeni.providers.router.describe",
        return_value="model: test-model",
    ):
        outcome, prompt = handle_slash_command("/model", [], None, None)
        assert outcome == CommandOutcome.HANDLED
        assert prompt is None
        assert "test-model" in capsys.readouterr().out


def test_handle_slash_command_compact(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Command /compact compacts session messages and reports tokens."""
    messages: list[Message] = [
        SystemMessage(content="system prompt"),
        UserMessage(content="msg1"),
    ]
    outcome, prompt = handle_slash_command("/compact", messages, None, None)
    assert outcome == CommandOutcome.HANDLED
    assert prompt is None
    captured = capsys.readouterr().out
    assert "tokens" in captured


def test_handle_slash_command_task() -> None:
    """Command /task returns prompt to be executed by agent loop."""
    outcome, prompt = handle_slash_command(
        "/task Implement feature X", [], None, None
    )
    assert outcome == CommandOutcome.RUN_PROMPT
    assert prompt == "Implement feature X"


def test_handle_slash_command_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unknown slash commands print a helpful error."""
    outcome, prompt = handle_slash_command("/unknown_cmd", [], None, None)
    assert outcome == CommandOutcome.HANDLED
    assert prompt is None
    captured = capsys.readouterr().out
    assert "Unknown command" in captured


def test_run_repl_execution(tmp_path: Path) -> None:
    """run_repl drives loop, handles prompts and commands, exits on /exit."""
    store = SessionStore.create(tmp_path, sessions_root=tmp_path / "sessions")
    context = HookContext(agent_role="reviewer", session_id=store.session_id)
    messages: list[Message] = [SystemMessage(content="System")]

    with create_pipe_input() as pipe_input:
        session = create_prompt_session(
            history=InMemoryHistory(),
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_text("Hello agent\r/exit\r")

        with patch("pelmeni.loop.run", return_value="Agent reply") as mock_run:
            run_repl(messages, store, context, prompt_session=session)
            mock_run.assert_called_once()
            assert len(messages) == 2
            assert messages[1].content == "Hello agent"

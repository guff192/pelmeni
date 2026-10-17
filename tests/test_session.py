"""Tests for project session hierarchy, main trace, line-1 header, and subagent logs."""

from __future__ import annotations

import json
from pathlib import Path

import logging

from pelmeni.domain import (
    AgentType,
    AssistantMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
    message_to_dto,
)
from pelmeni.dto.session import SessionHeader
from pelmeni.session import (
    SessionStore,
    SubagentLogger,
    derive_session_path,
    find_latest_session,
    open_session,
    read_session_messages,
    read_session_rounds,
    slugify_workspace,
)


def test_slugify_workspace_valid_names() -> None:
    """Workspace paths produce clean, sanitized alphanumeric slugs."""
    assert slugify_workspace(Path("/home/user/projects/pelmeni")) == "pelmeni"
    assert (
        slugify_workspace(Path("/var/opt/My_Project.Web!")) == "my-project-web"
    )
    assert slugify_workspace(Path("/")) == "root"


def test_derive_session_path_structure(tmp_path: Path) -> None:
    """Session path matches structure ~/.pelmeni/sessions/<project>/<id>/."""
    workspace = tmp_path / "my-awesome-repo"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions_root"

    session_dir, project_name, session_id = derive_session_path(
        workspace,
        sessions_root=sessions_root,
    )

    assert project_name == "my-awesome-repo"
    assert session_dir.parent == sessions_root / "my-awesome-repo"
    parts = session_dir.name.split("_")
    assert len(parts) >= 3
    assert parts[0].isalnum()
    assert parts[1] == "my-awesome-repo"
    assert len(parts[2]) >= 8
    assert session_id == session_dir.name


def test_session_store_create_initializes_directories(tmp_path: Path) -> None:
    """Creating SessionStore creates project, session, and subagents dirs."""
    workspace = tmp_path / "test-workspace"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)

    assert store.dir.exists()
    assert store.dir.is_dir()
    assert store.subagents_dir.exists()
    assert store.subagents_dir.is_dir()
    assert store.subagents_dir == store.dir / "subagents"
    assert store.main_log_file == store.dir / "main.jsonl"
    assert store.session_id == store.dir.name
    assert store.project_name == "test-workspace"


def test_session_store_writes_line_1_header(tmp_path: Path) -> None:
    """SessionStore automatically writes session_header on initialization."""
    workspace = tmp_path / "sample-app"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    header = store.ensure_header(
        initial_agent=AgentType.REVIEWER,
        metadata={"custom_key": "custom_val"},
    )

    assert header.session_id == store.session_id
    assert store.main_log_file.exists()
    lines = store.main_log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    first_record = json.loads(lines[0])
    assert first_record["event"] == "session_header"
    assert first_record["session_id"] == store.session_id
    assert first_record["workspace"] == str(workspace.resolve())
    assert first_record["initial_agent"] == "reviewer"
    assert first_record["metadata"]["custom_key"] == "custom_val"
    assert "created_at" in first_record

    read_back = store.read_header()
    assert read_back is not None
    assert read_back.session_id == store.session_id
    assert read_back.workspace == str(workspace.resolve())
    assert read_back.initial_agent == AgentType.REVIEWER


def test_session_store_ensure_header_is_idempotent(tmp_path: Path) -> None:
    """Calling ensure_header multiple times does not write duplicate headers."""
    workspace = tmp_path / "sample-app"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()
    store.ensure_header()

    lines = store.main_log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_session_store_log_event_appends_to_main_jsonl(tmp_path: Path) -> None:
    """Logging events writes JSON lines with timestamps and event payloads."""
    workspace = tmp_path / "project-x"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()
    store.log("request", {"messages": [{"role": "user", "content": "hi"}]})
    store.log("response", {"choices": [{"message": {"content": "hello"}}]})

    lines = store.main_log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["event"] == "session_header"
    assert json.loads(lines[1])["event"] == "request"
    assert json.loads(lines[2])["event"] == "response"


def test_create_subagent_log_creates_isolated_file(tmp_path: Path) -> None:
    """Subagent logger creates dedicated file without contaminating main."""
    workspace = tmp_path / "multi-agent-project"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()

    sub_logger = store.create_subagent_log(AgentType.INVESTIGATOR)
    assert isinstance(sub_logger, SubagentLogger)
    assert sub_logger.log_file.parent == store.subagents_dir
    file_name = sub_logger.log_file.name
    assert file_name.startswith("investigator_")
    assert file_name.endswith(".jsonl")

    sub_logger.log("subagent_start", {"goal": "inspect files"})
    sub_logger.log("tool_result", {"tool": "read", "output": "found code"})

    sub_lines = sub_logger.log_file.read_text(encoding="utf-8").splitlines()
    assert len(sub_lines) == 2
    assert json.loads(sub_lines[0])["event"] == "subagent_start"
    assert json.loads(sub_lines[1])["event"] == "tool_result"

    main_lines = store.main_log_file.read_text(encoding="utf-8").splitlines()
    assert len(main_lines) == 1
    assert json.loads(main_lines[0])["event"] == "session_header"


def test_multiple_subagents_isolated_from_each_other(tmp_path: Path) -> None:
    """Multiple subagents create independent files without collisions."""
    workspace = tmp_path / "multi-subagent"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)

    sub1 = store.create_subagent_log(AgentType.BUILDER)
    sub2 = store.create_subagent_log(AgentType.TESTER)

    assert sub1.log_file != sub2.log_file
    sub1.log("builder_event", {"diff": "+line"})
    sub2.log("tester_event", {"status": "passed"})

    assert len(sub1.log_file.read_text(encoding="utf-8").splitlines()) == 1
    assert len(sub2.log_file.read_text(encoding="utf-8").splitlines()) == 1
    assert "builder_event" in sub1.log_file.read_text(encoding="utf-8")
    assert "tester_event" in sub2.log_file.read_text(encoding="utf-8")


def test_session_store_open_existing(tmp_path: Path) -> None:
    """Opening an existing session directory restores the SessionStore."""
    workspace = tmp_path / "existing-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header(initial_agent=AgentType.MANAGER)
    store.log("turn_1", {"data": 123})

    reopened = open_session(store.dir)
    assert reopened.dir == store.dir
    assert reopened.session_id == store.session_id
    assert reopened.subagents_dir == store.subagents_dir
    header = reopened.read_header()
    assert header is not None
    assert header.initial_agent == AgentType.MANAGER


def test_session_header_conversation_id_field() -> None:
    """SessionHeader supports optional bridge conversation_id field."""
    header = SessionHeader(
        session_id="sess-1",
        workspace="/test",
        created_at=1000.0,
        conversation_id="conv-uuid-1",
    )
    assert header.conversation_id == "conv-uuid-1"
    dumped = header.model_dump()
    assert dumped["conversation_id"] == "conv-uuid-1"


def test_update_bridge_conversation_id_flushes_to_header(
    tmp_path: Path,
) -> None:
    """Updating conversation_id flushes directly into line-1 header."""
    workspace = tmp_path / "bridge-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    initial_header = store.ensure_header()
    assert initial_header.conversation_id is None

    store.update_bridge_conversation_id("agy-uuid-999")

    # Fast O(1) header read returns updated conversation_id
    updated_header = store.read_header()
    assert updated_header is not None
    assert updated_header.conversation_id == "agy-uuid-999"

    # Line 1 in main.jsonl physically contains conversation_id
    first_line = store.main_log_file.read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(first_line)
    assert parsed["event"] == "session_header"
    assert parsed["conversation_id"] == "agy-uuid-999"


def test_update_bridge_conversation_id_preserves_subsequent_events(
    tmp_path: Path,
) -> None:
    """Updating conversation_id preserves subsequent events."""
    workspace = tmp_path / "bridge-events-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "pelmeni-sessions"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()
    store.log("request", {"prompt": "turn 1 prompt"})
    store.log("response", {"answer": "turn 1 answer"})

    store.update_bridge_conversation_id("agy-uuid-preserved")

    lines = store.main_log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["conversation_id"] == "agy-uuid-preserved"
    assert json.loads(lines[1])["event"] == "request"
    assert json.loads(lines[2])["event"] == "response"


def test_find_latest_session_returns_none_if_no_sessions(
    tmp_path: Path,
) -> None:
    """find_latest_session returns None when no project directory exists."""
    workspace = tmp_path / "empty-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions-root"
    assert find_latest_session(workspace, sessions_root=sessions_root) is None


def test_find_latest_session_discovers_latest_by_timestamp(
    tmp_path: Path,
) -> None:
    """find_latest_session returns session directory with latest timestamp."""
    workspace = tmp_path / "my-workspace"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions-root"
    project_slug = slugify_workspace(workspace)
    proj_dir = sessions_root / project_slug
    proj_dir.mkdir(parents=True)

    session_older = proj_dir / "20261017T100000Z_my-workspace_abc12345"
    session_middle = proj_dir / "20261017T110000Z_my-workspace_def67890"
    session_newest = proj_dir / "20261017T120000Z_my-workspace_fff00000"

    for s_dir in (session_older, session_middle, session_newest):
        s_dir.mkdir()
        (s_dir / "main.jsonl").write_text("{}\n", encoding="utf-8")

    (proj_dir / "random_file.txt").write_text("ignore", encoding="utf-8")

    latest = find_latest_session(workspace, sessions_root=sessions_root)
    assert latest == session_newest


def test_read_header_extracts_line_1_without_reading_entire_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_header calls readline exactly once without reading subsequent lines."""
    workspace = tmp_path / "large-log-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions-root"
    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header(initial_agent=AgentType.BUILDER)

    with store.main_log_file.open("a", encoding="utf-8") as handle:
        for index in range(500):
            handle.write(json.dumps({"ts": index, "event": "dummy"}) + "\n")

    readline_calls = 0
    read_calls = 0
    readlines_calls = 0
    original_open = Path.open

    def instrumented_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        file_obj = original_open(self, *args, **kwargs)
        if (
            self == store.main_log_file
            and "r" in args
            or kwargs.get("mode") == "r"
        ):
            nonlocal readline_calls, read_calls, readlines_calls
            orig_readline = file_obj.readline
            orig_read = file_obj.read
            orig_readlines = file_obj.readlines

            def tracked_readline(*r_args: object, **r_kwargs: object) -> str:
                nonlocal readline_calls
                readline_calls += 1
                return orig_readline(*r_args, **r_kwargs)

            def tracked_read(*r_args: object, **r_kwargs: object) -> str:
                nonlocal read_calls
                read_calls += 1
                return orig_read(*r_args, **r_kwargs)

            def tracked_readlines(
                *r_args: object, **r_kwargs: object
            ) -> list[str]:
                nonlocal readlines_calls
                readlines_calls += 1
                return orig_readlines(*r_args, **r_kwargs)

            monkeypatch.setattr(file_obj, "readline", tracked_readline)
            monkeypatch.setattr(file_obj, "read", tracked_read)
            monkeypatch.setattr(file_obj, "readlines", tracked_readlines)
        return file_obj

    monkeypatch.setattr(Path, "open", instrumented_open)

    header = store.read_header()
    assert header is not None
    assert header.initial_agent == AgentType.BUILDER
    assert header.session_id == store.session_id
    assert readline_calls == 1
    assert read_calls == 0
    assert readlines_calls == 0


def test_read_messages_and_read_rounds_reconstruct_domain_entities(
    tmp_path: Path,
) -> None:
    """read_messages and read_rounds correctly reconstruct conversation."""
    workspace = tmp_path / "reconstruction-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions-root"
    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()

    sys_msg = SystemMessage(content="You are pelmeni.")
    user_msg_1 = UserMessage(content="Hello!")
    tool_call = ToolCall(id="tc-1", name="read", arguments='{"path": "a.txt"}')
    assistant_msg_1 = AssistantMessage(content=None, tool_calls=(tool_call,))
    tool_msg = ToolMessage(tool_call_id="tc-1", content="file content")
    assistant_msg_2 = AssistantMessage(content="Read done", tool_calls=())
    user_msg_2 = UserMessage(content="Next step")
    assistant_msg_3 = AssistantMessage(content="Finished", tool_calls=())

    store.log(
        "request",
        {"messages": [message_to_dto(sys_msg), message_to_dto(user_msg_1)]},
    )
    store.log("response", message_to_dto(assistant_msg_1))
    store.log("tool_result", message_to_dto(tool_msg))
    store.log("response", message_to_dto(assistant_msg_2))

    store.log(
        "request",
        {
            "messages": [
                message_to_dto(sys_msg),
                message_to_dto(user_msg_1),
                message_to_dto(assistant_msg_1),
                message_to_dto(tool_msg),
                message_to_dto(assistant_msg_2),
                message_to_dto(user_msg_2),
            ],
        },
    )
    store.log("response", message_to_dto(assistant_msg_3))

    reconstructed_messages = read_session_messages(store)
    expected_messages = [
        sys_msg,
        user_msg_1,
        assistant_msg_1,
        tool_msg,
        assistant_msg_2,
        user_msg_2,
        assistant_msg_3,
    ]
    assert reconstructed_messages == expected_messages

    rounds = read_session_rounds(store)
    assert len(rounds) == 2
    assert rounds[0].user == user_msg_1
    assert rounds[0].turns == (assistant_msg_1, tool_msg, assistant_msg_2)
    assert rounds[1].user == user_msg_2
    assert rounds[1].turns == (assistant_msg_3,)


def test_corrupted_lines_are_logged_and_skipped(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed or invalid JSON lines are safely skipped and logged."""
    workspace = tmp_path / "corrupted-log-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions-root"
    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()

    user_msg = UserMessage(content="Valid question")
    store.log("user_message", message_to_dto(user_msg))

    with store.main_log_file.open("a", encoding="utf-8") as handle:
        handle.write("THIS IS NOT JSON\n")
        handle.write(json.dumps({"event": "unknown_event_type"}) + "\n")
        handle.write(
            json.dumps({"event": "request", "messages": "not-a-list"}) + "\n",
        )

    assistant_msg = AssistantMessage(content="Valid reply", tool_calls=())
    store.log("response", message_to_dto(assistant_msg))

    with caplog.at_level(logging.WARNING):
        messages = read_session_messages(store)

    assert user_msg in messages
    assert assistant_msg in messages
    assert any(
        "corrupt" in rec.message.lower() or "skip" in rec.message.lower()
        for rec in caplog.records
    )


def test_session_store_write_read_roundtrip(tmp_path: Path) -> None:
    """Full roundtrip logging turns to SessionStore and reading back."""
    workspace = tmp_path / "roundtrip-proj"
    workspace.mkdir()
    sessions_root = tmp_path / "sessions-root"

    store = SessionStore.create(workspace, sessions_root=sessions_root)
    store.ensure_header()

    sys_msg = SystemMessage(content="System prompt")
    u1 = UserMessage(content="User query 1")
    tc1 = ToolCall(id="c1", name="glob", arguments='{"pattern": "*.py"}')
    a1 = AssistantMessage(content="Let me check", tool_calls=(tc1,))
    t1 = ToolMessage(tool_call_id="c1", content="file.py")
    a2 = AssistantMessage(content="Found file.py", tool_calls=())

    store.log(
        "request",
        {"messages": [message_to_dto(sys_msg), message_to_dto(u1)]},
    )
    store.log(
        "response",
        {"choices": [{"message": message_to_dto(a1)}]},
    )
    store.log("tool_result", {"tool_call_id": "c1", "result": "file.py"})
    store.log(
        "response",
        {"choices": [{"message": message_to_dto(a2)}]},
    )

    loaded_messages = read_session_messages(store)
    assert loaded_messages == [sys_msg, u1, a1, t1, a2]

    loaded_rounds = read_session_rounds(store)
    assert len(loaded_rounds) == 1
    assert loaded_rounds[0].user == u1
    assert loaded_rounds[0].turns == (a1, t1, a2)

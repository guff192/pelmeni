"""Tests for project session hierarchy, main trace, line-1 header, and subagent logs."""

from __future__ import annotations

import json
from pathlib import Path

from pelmeni.domain import AgentType
from pelmeni.session import (
    SessionStore,
    SubagentLogger,
    derive_session_path,
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

    reopened = SessionStore.open(store.dir)
    assert reopened.dir == store.dir
    assert reopened.session_id == store.session_id
    assert reopened.subagents_dir == store.subagents_dir
    header = reopened.read_header()
    assert header is not None
    assert header.initial_agent == AgentType.MANAGER

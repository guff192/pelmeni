"""Project-scoped session directory hierarchy and session log management."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pelmeni import domain, dto

DEFAULT_SESSIONS_ROOT = Path.home() / ".pelmeni" / "sessions"
_MAIN_LOG_NAME = "main.jsonl"
_SUBAGENTS_DIR_NAME = "subagents"
_SHORT_HASH_LEN = 8
_UTF8 = "utf-8"
_EVENT_KEY = "event"
_ROLE_KEY = "role"


def slugify_workspace(workspace: Path) -> str:
    """Derive a clean, URL/file-safe alphanumeric slug for a workspace path."""
    name = workspace.resolve().name
    if not name:
        return "root"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")
    return slug or "workspace"


def _generate_session_id(project_slug: str) -> str:
    timestamp_prefix = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    random_entropy = f"{time.time()}-{uuid.uuid4()}"
    digest = sha256(random_entropy.encode()).hexdigest()[:_SHORT_HASH_LEN]
    return f"{timestamp_prefix}_{project_slug}_{digest}"


def derive_session_path(
    workspace: Path,
    sessions_root: Path | None = None,
) -> tuple[Path, str, str]:
    """Derive the project session directory path, project slug, and session ID.

    Format: <sessions_root>/<project>/<timestamp>_<slug>_<hash>/
    """
    root = sessions_root or DEFAULT_SESSIONS_ROOT
    project_slug = slugify_workspace(workspace)
    session_id = _generate_session_id(project_slug)
    session_dir = root / project_slug / session_id
    return session_dir, project_slug, session_id


def find_latest_session(
    workspace: Path,
    sessions_root: Path | None = None,
) -> Path | None:
    """Discover the latest session directory for a workspace."""
    root = sessions_root or DEFAULT_SESSIONS_ROOT
    project_slug = slugify_workspace(workspace)
    project_dir = root / project_slug
    if not project_dir.is_dir():
        return None

    session_dirs = [
        candidate
        for candidate in project_dir.iterdir()
        if candidate.is_dir() and (candidate / _MAIN_LOG_NAME).is_file()
    ]
    if not session_dirs:
        return None

    return max(session_dirs, key=lambda candidate: candidate.name)


class SubagentLogger:
    """Isolated session log writer for subagent tasks and executions."""

    def __init__(self, log_file: Path, agent_type: str) -> None:
        self.log_file = log_file
        self.agent_type = agent_type

    def log(self, event: str, trace_data: dict[str, Any] | None = None) -> None:
        """Append an event record to the subagent JSONL log file."""
        record_data = trace_data or {}
        event_dict: dict[str, Any] = {
            "ts": time.time(),
            "agent_type": self.agent_type,
            _EVENT_KEY: event,
        }
        event_dict.update(record_data)
        line = json.dumps(
            event_dict,
            ensure_ascii=False,
            default=str,
        )
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding=_UTF8) as file_handle:
            file_handle.write(f"{line}\n")


logger = logging.getLogger(__name__)


def _rewrite_main_header(log_file: Path, header_line: str) -> None:  # noqa: WPS210
    other_lines: list[str] = []
    if log_file.exists():
        with log_file.open("r", encoding=_UTF8) as read_handle:
            file_lines = read_handle.readlines()
            if len(file_lines) > 1:
                other_lines = file_lines[1:]

    temp_file = log_file.with_suffix(".tmp")
    with temp_file.open("w", encoding=_UTF8) as write_handle:
        write_handle.write(f"{header_line}\n")
        for remaining in other_lines:
            write_handle.write(remaining)

    temp_file.replace(log_file)


def _extract_response_messages(payload: dict[str, Any]) -> list[domain.Message]:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice_msg = choices[0].get("message")
        if isinstance(choice_msg, dict):
            return [domain.message_from_dto(choice_msg)]
    if _ROLE_KEY in payload:
        return [domain.message_from_dto(payload)]
    return []


def _extract_tool_messages(payload: dict[str, Any]) -> list[domain.Message]:
    if "tool_call_id" in payload and "result" in payload:
        tool_dict = {
            _ROLE_KEY: "tool",
            "tool_call_id": payload["tool_call_id"],
            "content": payload["result"],
        }
        return [domain.message_from_dto(tool_dict)]
    if _ROLE_KEY in payload:
        return [domain.message_from_dto(payload)]
    return []


def _parse_event_messages(payload: dict[str, Any]) -> list[domain.Message]:
    event_type = payload.get(_EVENT_KEY)
    if event_type == "request":
        raw_msgs = payload.get("messages")
        if isinstance(raw_msgs, list):
            return [domain.message_from_dto(raw) for raw in raw_msgs]
    if event_type == "response":
        return _extract_response_messages(payload)
    if event_type == "tool_result":
        return _extract_tool_messages(payload)
    if (
        event_type in {"user_message", "assistant_message"}
        and _ROLE_KEY in payload
    ):
        return [domain.message_from_dto(payload)]
    return []


def _parse_log_line(line: str) -> list[domain.Message]:
    trimmed = line.strip()
    if not trimmed:
        return []
    try:
        parsed_record = json.loads(trimmed)
    except json.JSONDecodeError, ValueError:
        logger.warning(
            "Skipping corrupted unparseable JSON line in session log"
        )
        return []

    if not isinstance(parsed_record, dict):
        logger.warning("Skipping non-dict record in session log")
        return []

    try:
        return _parse_event_messages(parsed_record)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "Skipping unparseable message payload in session log: %s",
            exc,
        )
        return []


def _find_prefix_overlap(
    current: list[domain.Message], incoming: list[domain.Message]
) -> int:
    common_len = 0
    max_check = min(len(current), len(incoming))
    while (
        common_len < max_check and current[common_len] == incoming[common_len]
    ):
        common_len += 1
    return common_len


def _append_unique_suffix(
    base: list[domain.Message],
    incoming: list[domain.Message],
    overlap: int,
) -> list[domain.Message]:
    merged = list(base)
    for msg in incoming[overlap:]:
        if not merged or merged[-1] != msg:
            merged.append(msg)
    return merged


def _find_suffix_overlap(
    current: list[domain.Message], incoming: list[domain.Message]
) -> int:
    for start_idx, _ in enumerate(current):
        suffix = current[start_idx:]
        if incoming[: len(suffix)] == suffix:
            return len(suffix)
    return 0


def _merge_messages(
    current: list[domain.Message],
    incoming: list[domain.Message],
) -> list[domain.Message]:
    """Merge an incoming message sequence into the accumulated message list."""
    if not current:
        return list(incoming)
    if not incoming:
        return current

    prefix_len = _find_prefix_overlap(current, incoming)
    if prefix_len > 0:
        return _append_unique_suffix(current, incoming, prefix_len)

    suffix_len = _find_suffix_overlap(current, incoming)
    if suffix_len > 0:
        merged = list(current)
        merged.extend(incoming[suffix_len:])
        return merged

    return _append_unique_suffix(current, incoming, 0)


class SessionStore:  # noqa: WPS214
    """Manages project-scoped session directory hierarchy and session logs."""

    def __init__(
        self,
        session_dir: Path,
        workspace: Path | None = None,
    ) -> None:
        self.dir = session_dir
        self.workspace = workspace
        self.session_id = session_dir.name
        self.project_name = session_dir.parent.name
        self.main_log_file = self.dir / _MAIN_LOG_NAME
        self.subagents_dir = self.dir / _SUBAGENTS_DIR_NAME

    @classmethod
    def create(
        cls,
        workspace: Path,
        sessions_root: Path | None = None,
    ) -> SessionStore:
        """Create a new session directory on disk with subagents folder."""
        session_dir, _, _ = derive_session_path(
            workspace,
            sessions_root=sessions_root,
        )
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / _SUBAGENTS_DIR_NAME).mkdir(parents=True, exist_ok=True)
        return cls(session_dir=session_dir, workspace=workspace)

    @classmethod
    def open(
        cls,
        session_dir: Path,
        workspace: Path | None = None,
    ) -> SessionStore:
        """Open an existing session directory."""
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / _SUBAGENTS_DIR_NAME).mkdir(parents=True, exist_ok=True)
        return cls(session_dir=session_dir, workspace=workspace)

    def ensure_header(
        self,
        initial_agent: domain.AgentType = domain.AgentType.REVIEWER,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dto.SessionHeader:
        """Ensure line-1 header record exists in main.jsonl."""
        existing = self.read_header()
        if existing is not None:
            return existing

        workspace_path = (
            str(self.workspace.resolve())
            if self.workspace
            else str(Path.cwd().resolve())
        )
        header = dto.SessionHeader(
            session_id=self.session_id,
            workspace=workspace_path,
            created_at=time.time(),
            initial_agent=initial_agent,
            conversation_id=conversation_id,
            metadata=metadata or {},
        )
        line = json.dumps(header.model_dump(), ensure_ascii=False, default=str)
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.main_log_file.open("a", encoding=_UTF8) as file_handle:
            file_handle.write(f"{line}\n")
        return header

    def update_bridge_conversation_id(self, conversation_id: str) -> None:
        """Record the remote bridge conversation_id in the session header."""
        self.dir.mkdir(parents=True, exist_ok=True)
        existing = self.read_header()
        if existing is None:
            self.ensure_header(conversation_id=conversation_id)
            return

        existing.conversation_id = conversation_id
        if existing.metadata.get("conversation_id"):
            existing.metadata["conversation_id"] = conversation_id

        header_line = json.dumps(
            existing.model_dump(),
            ensure_ascii=False,
            default=str,
        )
        _rewrite_main_header(self.main_log_file, header_line)

    def read_header(self) -> dto.SessionHeader | None:
        """Fast O(1) read of line 1 session_header record."""
        if not self.main_log_file.exists():
            return None
        with self.main_log_file.open("r", encoding=_UTF8) as file_handle:
            first_line = file_handle.readline().strip()
        if not first_line:
            return None
        try:
            parsed = json.loads(first_line)
        except json.JSONDecodeError, ValueError:
            return None
        if parsed.get("event") == "session_header":
            return dto.SessionHeader.model_validate(parsed)
        return None

    def log(self, event: str, trace_data: dict[str, Any] | None = None) -> None:
        """Append an event record to the primary session log."""
        record_data = trace_data or {}
        event_dict: dict[str, Any] = {"ts": time.time(), _EVENT_KEY: event}
        event_dict.update(record_data)
        line = json.dumps(
            event_dict,
            ensure_ascii=False,
            default=str,
        )
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.main_log_file.open("a", encoding=_UTF8) as file_handle:
            file_handle.write(f"{line}\n")

    def create_subagent_log(
        self,
        agent_type: domain.AgentType | str,
    ) -> SubagentLogger:
        """Create an isolated log file for a subagent invocation."""
        agent_name = (
            agent_type.value
            if isinstance(agent_type, domain.AgentType)
            else str(agent_type)
        )
        timestamp_part = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        short_id = uuid.uuid4().hex[:_SHORT_HASH_LEN]
        log_file_name = f"{agent_name}_{timestamp_part}_{short_id}.jsonl"
        log_file = self.subagents_dir / log_file_name
        return SubagentLogger(log_file=log_file, agent_type=agent_name)

    def read_messages(self) -> list[domain.Message]:
        """Parse main.jsonl and reconstruct unique ordered domain messages."""
        if not self.main_log_file.is_file():
            return []

        restored: list[domain.Message] = []
        with self.main_log_file.open("r", encoding=_UTF8) as log_handle:
            for line in log_handle:
                line_messages = _parse_log_line(line)
                restored = _merge_messages(restored, line_messages)
        return restored

    def read_rounds(self) -> list[domain.Round]:
        """Parse main.jsonl and group reconstructed messages into Rounds."""
        messages = self.read_messages()
        _, rounds = domain.group_into_rounds(messages)
        return rounds

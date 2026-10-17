"""Trace log deserializer and message sequence reconstruction."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pelmeni import domain

if TYPE_CHECKING:
    from pelmeni.session.store import SessionStore

logger = logging.getLogger(__name__)

_EVENT_KEY = "event"
_ROLE_KEY = "role"
_UTF8 = "utf-8"


def _extract_response_msg(payload: dict[str, Any]) -> list[domain.Message]:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice_msg = choices[0].get("message")
        if isinstance(choice_msg, dict):
            return [domain.message_from_dto(choice_msg)]
    return []


def _extract_messages_from_event(
    payload: dict[str, Any],
) -> list[domain.Message]:
    event_type = payload.get(_EVENT_KEY)
    if event_type == "request":
        raw_msgs = payload.get("messages")
        if isinstance(raw_msgs, list):
            return [domain.message_from_dto(raw) for raw in raw_msgs]
    if event_type == "response":
        resp_msgs = _extract_response_msg(payload)
        if resp_msgs:
            return resp_msgs
    if event_type == "tool_result" and "tool_call_id" in payload:
        tool_content = payload.get("result") or payload.get("content", "")
        return [
            domain.message_from_dto(
                {
                    _ROLE_KEY: "tool",
                    "tool_call_id": payload["tool_call_id"],
                    "content": tool_content,
                }
            ),
        ]
    if _ROLE_KEY in payload:
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
        return _extract_messages_from_event(parsed_record)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "Skipping unparseable message payload in session log: %s",
            exc,
        )
        return []


def _append_tail(
    base: list[domain.Message],
    incoming: list[domain.Message],
    start: int,
) -> list[domain.Message]:
    merged = list(base)
    for msg in incoming[start:]:
        if not merged or merged[-1] != msg:
            merged.append(msg)
    return merged


def _merge_messages(
    current: list[domain.Message],
    incoming: list[domain.Message],
) -> list[domain.Message]:
    """Merge an incoming message sequence into the accumulated message list."""
    if not current:
        return list(incoming)
    if not incoming:
        return current

    prefix_len = 0
    max_check = min(len(current), len(incoming))
    while (
        prefix_len < max_check and current[prefix_len] == incoming[prefix_len]
    ):
        prefix_len += 1
    if prefix_len > 0:
        return _append_tail(current, incoming, prefix_len)

    for start_idx, _ in enumerate(current):
        suffix = current[start_idx:]
        if incoming[: len(suffix)] == suffix:
            merged = list(current)
            merged.extend(incoming[len(suffix) :])
            return merged

    return _append_tail(current, incoming, 0)


def read_session_messages(
    target: Path | SessionStore,
) -> list[domain.Message]:
    """Parse main.jsonl and reconstruct unique ordered domain messages."""
    log_file = target if isinstance(target, Path) else target.main_log_file
    if not log_file.is_file():
        return []

    restored: list[domain.Message] = []
    with log_file.open("r", encoding=_UTF8) as log_handle:
        for line in log_handle:
            line_messages = _parse_log_line(line)
            restored = _merge_messages(restored, line_messages)
    return restored


def read_session_rounds(
    target: Path | SessionStore,
) -> list[domain.Round]:
    """Parse main.jsonl and group reconstructed messages into Rounds."""
    messages = read_session_messages(target)
    _, rounds = domain.group_into_rounds(messages)
    return rounds

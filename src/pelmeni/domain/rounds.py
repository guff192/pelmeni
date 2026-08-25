"""Round dataclass and conversation grouping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pelmeni.domain.messages import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_Segment = tuple[UserMessage, list[AssistantMessage | ToolMessage]]


@dataclass(frozen=True, slots=True)
class Round:
    """One complete request/response cycle in a conversation."""

    user: UserMessage
    turns: tuple[AssistantMessage | ToolMessage, ...] = ()

    @property
    def all_messages(
        self,
    ) -> list[UserMessage | AssistantMessage | ToolMessage]:
        """Return user message followed by every turn in order."""
        return [self.user, *self.turns]


def _segment_by_user(
    messages: list[Message],
) -> list[_Segment]:
    """Partition messages into (UserMessage, turns) pairs."""
    segments: list[_Segment] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            segments.append((msg, []))
        elif segments and isinstance(msg, (AssistantMessage, ToolMessage)):
            segments[-1][1].append(msg)
    return segments


def _collect_rounds(remaining: list[Message]) -> list[Round]:
    """Build a list of Rounds from a flat non-system message list."""
    return [
        Round(user=user, turns=tuple(turns))
        for user, turns in _segment_by_user(remaining)
    ]


def group_into_rounds(
    messages: Sequence[Message],
) -> tuple[SystemMessage | None, list[Round]]:
    """Group a flat message list into an optional system prompt and rounds.

    Each Round begins at a UserMessage.  AssistantMessage and
    ToolMessage entries that follow it are collected as turns.
    A leading SystemMessage is extracted and returned separately.
    """
    if not messages:
        return None, []

    system: SystemMessage | None = None
    turns_start = 0
    if messages and isinstance(messages[0], SystemMessage):
        system = messages[0]
        turns_start = 1
    remaining = list(messages[turns_start:])

    return system, _collect_rounds(remaining)

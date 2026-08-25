"""Tests for pure domain message models and DTO mappers."""

from __future__ import annotations

import pytest

from pelmeni.domain import (
    AssistantMessage,
    Round,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
    group_into_rounds,
    message_from_dto,
    message_to_dto,
)

# ---------------------------------------------------------------------------
# ToolCall
# ---------------------------------------------------------------------------


class TestToolCall:
    """Tests for the ToolCall domain dataclass."""

    def test_fields_accessible(self) -> None:
        """ToolCall exposes id, name, and arguments attributes."""
        tc = ToolCall(
            id="call_1",
            name="read_file",
            arguments='{"path": "/tmp/x"}',
        )
        assert tc.id == "call_1"
        assert tc.name == "read_file"
        assert tc.arguments == '{"path": "/tmp/x"}'

    def test_frozen_rejects_mutation(self) -> None:
        """ToolCall is immutable; attribute assignment must raise."""
        tc = ToolCall(id="c", name="fn", arguments="{}")
        with pytest.raises((AttributeError, TypeError)):
            tc.id = "other"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        """Two ToolCalls with identical fields compare equal."""
        a = ToolCall(id="c", name="fn", arguments="{}")
        b = ToolCall(id="c", name="fn", arguments="{}")
        assert a == b

    def test_inequality_on_differing_id(self) -> None:
        """ToolCalls with different ids are not equal."""
        a = ToolCall(id="c1", name="fn", arguments="{}")
        b = ToolCall(id="c2", name="fn", arguments="{}")
        assert a != b


# ---------------------------------------------------------------------------
# SystemMessage
# ---------------------------------------------------------------------------


class TestSystemMessage:
    """Tests for the SystemMessage domain dataclass."""

    def test_role_is_system(self) -> None:
        """SystemMessage.role is always 'system'."""
        msg = SystemMessage(content="You are helpful.")
        assert msg.role == "system"

    def test_content_stored(self) -> None:
        """SystemMessage stores provided content verbatim."""
        msg = SystemMessage(content="Be concise.")
        assert msg.content == "Be concise."

    def test_frozen_rejects_mutation(self) -> None:
        """SystemMessage is immutable."""
        msg = SystemMessage(content="x")
        with pytest.raises((AttributeError, TypeError)):
            msg.content = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UserMessage
# ---------------------------------------------------------------------------


class TestUserMessage:
    """Tests for the UserMessage domain dataclass."""

    def test_role_is_user(self) -> None:
        """UserMessage.role is always 'user'."""
        msg = UserMessage(content="Hello.")
        assert msg.role == "user"

    def test_content_stored(self) -> None:
        """UserMessage stores provided content verbatim."""
        msg = UserMessage(content="Fix the bug.")
        assert msg.content == "Fix the bug."

    def test_frozen_rejects_mutation(self) -> None:
        """UserMessage is immutable."""
        msg = UserMessage(content="x")
        with pytest.raises((AttributeError, TypeError)):
            msg.content = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AssistantMessage
# ---------------------------------------------------------------------------


class TestAssistantMessage:
    """Tests for the AssistantMessage domain dataclass."""

    def test_role_is_assistant(self) -> None:
        """AssistantMessage.role is always 'assistant'."""
        msg = AssistantMessage(content="Done.", tool_calls=())
        assert msg.role == "assistant"

    def test_tool_calls_is_tuple(self) -> None:
        """tool_calls is a tuple of ToolCall instances."""
        tc = ToolCall(id="c1", name="fn", arguments="{}")
        msg = AssistantMessage(content=None, tool_calls=(tc,))
        assert isinstance(msg.tool_calls, tuple)
        assert msg.tool_calls[0] is tc

    def test_empty_tool_calls(self) -> None:
        """AssistantMessage accepts an empty tuple of tool_calls."""
        msg = AssistantMessage(content="Plain text.", tool_calls=())
        assert msg.tool_calls == ()

    def test_none_content_allowed(self) -> None:
        """AssistantMessage content may be None when tool_calls present."""
        tc = ToolCall(id="c", name="fn", arguments="{}")
        msg = AssistantMessage(content=None, tool_calls=(tc,))
        assert msg.content is None

    def test_frozen_rejects_mutation(self) -> None:
        """AssistantMessage is immutable."""
        msg = AssistantMessage(content="x", tool_calls=())
        with pytest.raises((AttributeError, TypeError)):
            msg.content = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ToolMessage
# ---------------------------------------------------------------------------


class TestToolMessage:
    """Tests for the ToolMessage domain dataclass."""

    def test_role_is_tool(self) -> None:
        """ToolMessage.role is always 'tool'."""
        msg = ToolMessage(tool_call_id="c1", content="ok")
        assert msg.role == "tool"

    def test_fields_accessible(self) -> None:
        """ToolMessage exposes tool_call_id and content."""
        msg = ToolMessage(tool_call_id="c1", content="result")
        assert msg.tool_call_id == "c1"
        assert msg.content == "result"

    def test_frozen_rejects_mutation(self) -> None:
        """ToolMessage is immutable."""
        msg = ToolMessage(tool_call_id="c", content="x")
        with pytest.raises((AttributeError, TypeError)):
            msg.content = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Round
# ---------------------------------------------------------------------------


class TestRound:
    """Tests for the Round domain dataclass."""

    def _make_round(self) -> Round:
        """Build a minimal Round with one assistant and one tool turn."""
        user = UserMessage(content="Do it.")
        tc = ToolCall(id="c1", name="fn", arguments="{}")
        assistant = AssistantMessage(content=None, tool_calls=(tc,))
        tool_result = ToolMessage(tool_call_id="c1", content="done")
        return Round(user=user, turns=(assistant, tool_result))

    def test_user_field(self) -> None:
        """Round.user holds the originating UserMessage."""
        rnd = self._make_round()
        assert rnd.user.role == "user"
        assert rnd.user.content == "Do it."

    def test_turns_is_tuple(self) -> None:
        """Round.turns is a tuple of AssistantMessage or ToolMessage."""
        rnd = self._make_round()
        assert isinstance(rnd.turns, tuple)
        assert len(rnd.turns) == 2

    def test_all_messages_starts_with_user(self) -> None:
        """Round.all_messages begins with the UserMessage."""
        rnd = self._make_round()
        msgs = rnd.all_messages
        assert msgs[0] is rnd.user

    def test_all_messages_contains_all_turns(self) -> None:
        """Round.all_messages includes every turn after the user message."""
        rnd = self._make_round()
        msgs = rnd.all_messages
        assert len(msgs) == 3
        assert msgs[1] is rnd.turns[0]
        assert msgs[2] is rnd.turns[1]

    def test_empty_turns_round(self) -> None:
        """Round with no turns yields a single-element all_messages."""
        user = UserMessage(content="Hi.")
        rnd = Round(user=user, turns=())
        assert rnd.all_messages == [user]

    def test_frozen_rejects_mutation(self) -> None:
        """Round is immutable."""
        rnd = self._make_round()
        with pytest.raises((AttributeError, TypeError)):
            rnd.user = UserMessage(content="other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# group_into_rounds
# ---------------------------------------------------------------------------


class TestGroupIntoRounds:
    """Tests for the group_into_rounds helper function."""

    def _system(self) -> SystemMessage:
        """Build a throwaway SystemMessage."""
        return SystemMessage(content="sys")

    def _user(self, text: str = "u") -> UserMessage:
        """Build a throwaway UserMessage."""
        return UserMessage(content=text)

    def _assistant(self, content: str = "a") -> AssistantMessage:
        """Build a throwaway AssistantMessage."""
        return AssistantMessage(content=content, tool_calls=())

    def _tool_result(self) -> ToolMessage:
        """Build a throwaway ToolMessage."""
        return ToolMessage(tool_call_id="c", content="res")

    def test_empty_list_returns_none_and_no_rounds(self) -> None:
        """Empty input yields (None, [])."""
        system, rounds = group_into_rounds([])
        assert system is None
        assert rounds == []

    def test_extracts_system_message(self) -> None:
        """Leading SystemMessage is returned separately."""
        msgs = [
            self._system(),
            self._user("q"),
            self._assistant("a"),
        ]
        system, _ = group_into_rounds(msgs)
        assert system is not None
        assert system.role == "system"

    def test_no_system_message_returns_none(self) -> None:
        """Absence of SystemMessage yields None for the first element."""
        msgs = [self._user("q"), self._assistant("a")]
        system, _ = group_into_rounds(msgs)
        assert system is None

    def test_single_round_no_system(self) -> None:
        """One user+assistant pair produces exactly one Round."""
        user = self._user("q")
        asst = self._assistant("a")
        _, rounds = group_into_rounds([user, asst])
        assert len(rounds) == 1
        assert rounds[0].user is user
        assert rounds[0].turns[0] is asst

    def test_round_groups_tool_turns(self) -> None:
        """ToolMessages following an assistant are grouped in the same Round."""
        user = self._user("q")
        tc = ToolCall(id="c1", name="fn", arguments="{}")
        asst = AssistantMessage(content=None, tool_calls=(tc,))
        res = ToolMessage(tool_call_id="c1", content="done")
        _, rounds = group_into_rounds([user, asst, res])
        assert len(rounds) == 1
        assert len(rounds[0].turns) == 2

    def test_multiple_rounds(self) -> None:
        """Sequential user messages each start a new Round."""
        msgs = [
            self._user("q1"),
            self._assistant("a1"),
            self._user("q2"),
            self._assistant("a2"),
        ]
        _, rounds = group_into_rounds(msgs)
        assert len(rounds) == 2
        assert rounds[0].user.content == "q1"
        assert rounds[1].user.content == "q2"

    def test_with_system_and_multiple_rounds(self) -> None:
        """System message plus multiple rounds are handled together."""
        msgs = [
            self._system(),
            self._user("q1"),
            self._assistant("a1"),
            self._user("q2"),
            self._assistant("a2"),
        ]
        system, rounds = group_into_rounds(msgs)
        assert system is not None
        assert len(rounds) == 2


# ---------------------------------------------------------------------------
# DTO mappers
# ---------------------------------------------------------------------------


class TestMessageToDto:
    """Tests for message_to_dto conversion."""

    def test_system_message_to_dto(self) -> None:
        """SystemMessage converts to a dict with role and content."""
        msg = SystemMessage(content="sys prompt")
        dto = message_to_dto(msg)
        assert dto["role"] == "system"
        assert dto["content"] == "sys prompt"

    def test_user_message_to_dto(self) -> None:
        """UserMessage converts to a dict with role and content."""
        msg = UserMessage(content="user text")
        dto = message_to_dto(msg)
        assert dto["role"] == "user"
        assert dto["content"] == "user text"

    def test_assistant_message_to_dto_with_content(self) -> None:
        """AssistantMessage with content converts to dict correctly."""
        msg = AssistantMessage(content="reply", tool_calls=())
        dto = message_to_dto(msg)
        assert dto["role"] == "assistant"
        assert dto["content"] == "reply"

    def test_assistant_message_to_dto_with_tool_calls(self) -> None:
        """AssistantMessage with tool_calls serialises calls into dto."""
        tc = ToolCall(id="c1", name="fn", arguments="{}")
        msg = AssistantMessage(content=None, tool_calls=(tc,))
        dto = message_to_dto(msg)
        assert dto["role"] == "assistant"
        calls = dto["tool_calls"]
        assert len(calls) == 1
        assert calls[0]["id"] == "c1"
        assert calls[0]["name"] == "fn"

    def test_tool_message_to_dto(self) -> None:
        """ToolMessage converts to a dict with role, id, and content."""
        msg = ToolMessage(tool_call_id="c1", content="done")
        dto = message_to_dto(msg)
        assert dto["role"] == "tool"
        assert dto["tool_call_id"] == "c1"
        assert dto["content"] == "done"


class TestMessageFromDto:
    """Tests for message_from_dto conversion."""

    def test_system_dto_to_domain(self) -> None:
        """Dict with role='system' produces a SystemMessage."""
        dto = {"role": "system", "content": "prompt"}
        msg = message_from_dto(dto)
        assert isinstance(msg, SystemMessage)
        assert msg.content == "prompt"

    def test_user_dto_to_domain(self) -> None:
        """Dict with role='user' produces a UserMessage."""
        dto = {"role": "user", "content": "hi"}
        msg = message_from_dto(dto)
        assert isinstance(msg, UserMessage)
        assert msg.content == "hi"

    def test_assistant_dto_to_domain(self) -> None:
        """Dict with role='assistant' produces an AssistantMessage."""
        dto = {"role": "assistant", "content": "done", "tool_calls": []}
        msg = message_from_dto(dto)
        assert isinstance(msg, AssistantMessage)
        assert msg.content == "done"
        assert msg.tool_calls == ()

    def test_assistant_dto_with_tool_calls(self) -> None:
        """AssistantMessage DTO with tool_calls deserialises correctly."""
        dto = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "name": "fn", "arguments": "{}"},
            ],
        }
        msg = message_from_dto(dto)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "c1"

    def test_tool_dto_to_domain(self) -> None:
        """Dict with role='tool' produces a ToolMessage."""
        dto = {"role": "tool", "tool_call_id": "c1", "content": "res"}
        msg = message_from_dto(dto)
        assert isinstance(msg, ToolMessage)
        assert msg.tool_call_id == "c1"

    def test_roundtrip_system(self) -> None:
        """SystemMessage survives a to_dto -> from_dto round-trip."""
        original = SystemMessage(content="prompt")
        restored = message_from_dto(message_to_dto(original))
        assert restored == original

    def test_roundtrip_user(self) -> None:
        """UserMessage survives a to_dto -> from_dto round-trip."""
        original = UserMessage(content="q")
        restored = message_from_dto(message_to_dto(original))
        assert restored == original

    def test_roundtrip_assistant_with_tool_calls(self) -> None:
        """AssistantMessage with tool_calls survives a round-trip."""
        tc = ToolCall(id="c1", name="fn", arguments='{"k":"v"}')
        original = AssistantMessage(content=None, tool_calls=(tc,))
        restored = message_from_dto(message_to_dto(original))
        assert restored == original

    def test_roundtrip_tool_message(self) -> None:
        """ToolMessage survives a to_dto -> from_dto round-trip."""
        original = ToolMessage(tool_call_id="c1", content="done")
        restored = message_from_dto(message_to_dto(original))
        assert restored == original

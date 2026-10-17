"""Integration tests for bridge conversation ID continuity in loop.run()."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from pelmeni import loop
from pelmeni.domain import Message, UserMessage
from pelmeni.session import SessionStore

if TYPE_CHECKING:
    from pathlib import Path


def test_loop_turn1_flushes_conversation_id_and_turn2_passes_it(
    tmp_path: Path,
) -> None:
    """Turn 1 flushes bridge conversation_id to header, Turn 2 reuses it."""
    workspace = tmp_path / "test-workspace"
    workspace.mkdir()
    store = SessionStore.create(workspace, sessions_root=tmp_path / "sessions")
    header = store.ensure_header()
    assert header.conversation_id is None

    # Mock provider.chat to simulate Turn 1 bridge execution
    def fake_chat_turn1(*_args: object, **kwargs: object) -> dict:
        on_init = kwargs.get("on_init")
        if callable(on_init):
            on_init("bridge-conv-uuid-123")
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "Turn 1 done"}},
            ],
            "conversation_id": "bridge-conv-uuid-123",
        }

    with patch(
        "pelmeni.loop.provider.chat",
        side_effect=fake_chat_turn1,
    ) as mock_chat:
        messages_turn1: list[Message] = [UserMessage(content="Hello Turn 1")]
        ans1 = loop.run(messages_turn1, store)
        assert ans1 == "Turn 1 done"

        # Verify Turn 1 had None as conversation_id and flushed to header
        assert mock_chat.call_args.kwargs.get("conversation_id") is None
        read_header = store.read_header()
        assert read_header is not None
        assert read_header.conversation_id == "bridge-conv-uuid-123"

    # Turn 2: verify loop.run passes the persisted conversation_id
    def fake_chat_turn2(*_args: object, **kwargs: object) -> dict:
        assert kwargs.get("conversation_id") == "bridge-conv-uuid-123"
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "Turn 2 done"}},
            ],
            "conversation_id": "bridge-conv-uuid-123",
        }

    with patch(
        "pelmeni.loop.provider.chat",
        side_effect=fake_chat_turn2,
    ) as mock_chat2:
        messages_turn2: list[Message] = [UserMessage(content="Hello Turn 2")]
        ans2 = loop.run(messages_turn2, store)
        assert ans2 == "Turn 2 done"
        assert (
            mock_chat2.call_args.kwargs.get("conversation_id")
            == "bridge-conv-uuid-123"
        )

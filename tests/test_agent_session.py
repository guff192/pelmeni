"""Tests for AgentSession execution module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from pelmeni.agent_session import (
    AgentSession,
    SessionConfig,
    create_agent_session,
)
from pelmeni.config.models import HookConfigSchema
from pelmeni.domain.agent_profiles import AgentProfile
from pelmeni.domain.agent_types import AgentType
from pelmeni.domain.messages import (
    AssistantMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from pelmeni.dto.context import CompactionConfigSchema
from pelmeni.dto.hooks import HookResult
from pelmeni.dto.tools import ToolSpec
from pelmeni.hooks.chain import HookChain
from pelmeni.session import SessionStore
from pelmeni.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from pathlib import Path


class DummyProvider:
    """Mock provider with controllable sequential responses."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        """Initialize dummy provider with optional responses."""
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Record request and return next sequential mock response."""
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Default response",
                        }
                    }
                ]
            }
        return self.responses.pop(0)


@pytest.fixture
def test_profile() -> AgentProfile:
    """Fixture providing a test builder agent profile."""
    return AgentProfile(
        agent_type=AgentType.BUILDER,
        name="builder",
        system_prompt="You are a builder.",
        allowed_tools=("read", "write"),
        model_alias="worker",
    )


@pytest.fixture
def temp_store(tmp_path: Path) -> SessionStore:
    """Fixture providing a temporary session store directory."""
    return SessionStore.create(tmp_path)


def test_agent_session_initializes_with_profile(
    test_profile: AgentProfile,
    temp_store: SessionStore,
) -> None:
    """AgentSession initializes message context with profile system prompt."""
    session = AgentSession(
        profile=test_profile,
        config=SessionConfig(provider=DummyProvider(), trace=temp_store),
    )
    assert session.profile == test_profile
    assert session.profile.agent_type == AgentType.BUILDER
    assert len(session.messages) == 1
    assert isinstance(session.messages[0], SystemMessage)
    assert session.messages[0].content == "You are a builder."


def test_agent_session_step_user_prompt(
    test_profile: AgentProfile,
    temp_store: SessionStore,
) -> None:
    """AgentSession.step() records user prompt and receives model reply."""
    provider = DummyProvider(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "I have created the file.",
                        }
                    }
                ]
            }
        ]
    )
    session = AgentSession(
        profile=test_profile,
        config=SessionConfig(provider=provider, trace=temp_store),
    )

    reply = session.step("Create main.py")

    assert reply == "I have created the file."
    assert len(session.messages) == 3
    assert isinstance(session.messages[1], UserMessage)
    assert session.messages[1].content == "Create main.py"
    assert isinstance(session.messages[2], AssistantMessage)
    assert session.messages[2].content == "I have created the file."
    assert len(provider.calls) == 1


def test_agent_session_step_executes_tool_calls(
    test_profile: AgentProfile,
    temp_store: SessionStore,
) -> None:
    """AgentSession.step() dispatches tool calls and appends ToolMessage."""
    tool_call_dict = {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "read",
            "arguments": '{"path": "hello.txt"}',
        },
    }
    provider = DummyProvider(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call_dict],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "File contents read.",
                        }
                    }
                ]
            },
        ]
    )

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read",
            description="Read file",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            handler=lambda path: f"content of {path}",
        ),
        roles=("builder",),
    )

    session = AgentSession(
        profile=test_profile,
        config=SessionConfig(
            provider=provider,
            trace=temp_store,
            registry=registry,
        ),
    )

    reply = session.step("Read hello.txt")

    assert reply == "File contents read."
    assert len(session.messages) == 5
    assert isinstance(session.messages[2], AssistantMessage)
    assert session.messages[2].tool_calls == (
        ToolCall(id="call_123", name="read", arguments='{"path": "hello.txt"}'),
    )
    assert isinstance(session.messages[3], ToolMessage)
    assert session.messages[3].tool_call_id == "call_123"
    assert session.messages[3].content == "content of hello.txt"
    assert isinstance(session.messages[4], AssistantMessage)
    assert session.messages[4].content == "File contents read."


def test_agent_session_scoped_hooks_deny_execution(
    test_profile: AgentProfile,
    temp_store: SessionStore,
) -> None:
    """AgentSession evaluates scoped hook chains and denies tool invocation."""
    tool_call_dict = {
        "id": "call_deny",
        "type": "function",
        "function": {
            "name": "read",
            "arguments": '{"path": "secret.txt"}',
        },
    }
    provider = DummyProvider(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call_dict],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Handled deny error.",
                        }
                    }
                ]
            },
        ]
    )

    deny_hook = MagicMock()
    deny_hook.name = "deny_all"
    deny_hook.return_value = HookResult(verdict="deny", reason="Access blocked")
    hook_chain = HookChain(
        [deny_hook],
        {"deny_all": HookConfigSchema()},
    )

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read",
            description="Read file",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            handler=lambda **_kwargs: "secret data",
        ),
        roles=("builder",),
    )

    session = AgentSession(
        profile=test_profile,
        config=SessionConfig(
            provider=provider,
            trace=temp_store,
            registry=registry,
            hook_chain=hook_chain,
        ),
    )

    session.step("Read secret")

    assert isinstance(session.messages[3], ToolMessage)
    assert (
        "error: blocked by hook: Access blocked" in session.messages[3].content
    )


def test_agent_session_independent_context_compaction(
    test_profile: AgentProfile,
    temp_store: SessionStore,
) -> None:
    """AgentSession compacts context independently without side effects."""
    reviewer_profile = AgentProfile(
        agent_type=AgentType.REVIEWER,
        name="reviewer",
        system_prompt="You are a reviewer.",
        allowed_tools=("read",),
        model_alias="planner",
    )

    provider1 = DummyProvider(
        responses=[
            {"choices": [{"message": {"role": "assistant", "content": "Done"}}]}
        ]
    )
    provider2 = DummyProvider(
        responses=[
            {"choices": [{"message": {"role": "assistant", "content": "Done"}}]}
        ]
    )

    compaction1 = CompactionConfigSchema(
        max_tokens=40,
        target_tokens=15,
        keep_recent_rounds=0,
    )
    compaction2 = CompactionConfigSchema(
        max_tokens=100_000,
        target_tokens=50_000,
    )

    session1 = AgentSession(
        profile=test_profile,
        config=SessionConfig(
            provider=provider1,
            trace=temp_store,
            compaction_config=compaction1,
        ),
    )
    session2 = AgentSession(
        profile=reviewer_profile,
        config=SessionConfig(
            provider=provider2,
            trace=temp_store,
            compaction_config=compaction2,
        ),
    )

    for i in range(10):
        session1.messages.append(
            UserMessage(content=f"Message {i} " + "long text " * 10)
        )
        session2.messages.append(
            UserMessage(content=f"Message {i} " + "long text " * 10)
        )

    initial_len1 = len(session1.messages)
    initial_len2 = len(session2.messages)

    session1.step("Next turn 1")
    session2.step("Next turn 2")

    assert len(session1.messages) < initial_len1
    assert len(session2.messages) > initial_len2


def test_create_agent_session_factory(
    temp_store: SessionStore,
) -> None:
    """create_agent_session constructs session with resolved AgentProfile."""
    session = create_agent_session(
        agent_type=AgentType.BUILDER,
        model_alias="worker",
        config=SessionConfig(provider=DummyProvider(), trace=temp_store),
    )
    assert session.profile.agent_type == AgentType.BUILDER
    assert session.profile.model_alias == "worker"
    assert len(session.messages) == 1
    assert isinstance(session.messages[0], SystemMessage)

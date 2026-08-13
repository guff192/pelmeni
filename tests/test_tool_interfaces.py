"""Contract tests for role-aware tool serialization and dispatch."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

from pelmeni import loop, tools
from pelmeni.dto.hooks import HookContext
from pelmeni.dto.tools import AgentRole, ToolParameterSchema, ToolSpec
from pelmeni.tools import ToolRegistry


def _tool(name: str, handler: MagicMock | None = None) -> ToolSpec:
    """Build a small executable tool specification."""
    return ToolSpec(
        name=name,
        description=f"Execute {name}.",
        parameters=ToolParameterSchema(
            properties={"value": {"type": "string"}},
            required=["value"],
        ),
        handler=handler,
    )


def _tool_call(name: str, **arguments: str) -> dict:
    """Build a provider-format function tool call."""
    return {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def _context(role: AgentRole) -> HookContext:
    """Build a dispatch context for one agent role."""
    return HookContext(agent_role=role, session_id="interface-tests")


def test_registry_serializes_function_tools_for_role() -> None:
    """Allowed specifications are serialized in provider function format."""
    registry = ToolRegistry()
    registry.register(
        _tool("read_file"),
        roles=[AgentRole.INVESTIGATOR],
    )

    assert registry.get_serialized_tools(AgentRole.INVESTIGATOR) == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Execute read_file.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]


def test_registry_accepts_string_role_and_filters_whitelist() -> None:
    """String roles resolve to the same whitelist as enum roles."""
    registry = ToolRegistry()
    registry.register(_tool("inspect"), roles=[AgentRole.INVESTIGATOR])
    registry.register(_tool("write"), roles=[AgentRole.BUILDER])

    investigator_tools = registry.get_serialized_tools("investigator")

    assert [item["function"]["name"] for item in investigator_tools] == [
        "inspect",
    ]
    assert registry.get_serialized_tools(AgentRole.REVIEWER) == []


def test_dispatch_executes_tool_allowed_for_context_role() -> None:
    """Dispatch invokes the registered handler after permission succeeds."""
    handler = MagicMock(return_value="completed")
    registry = ToolRegistry()
    registry.register(_tool("write", handler), roles=[AgentRole.BUILDER])

    result = tools.dispatch(
        _tool_call("write", value="content"),
        _context(AgentRole.BUILDER),
        registry,
    )

    assert result == "completed"
    handler.assert_called_once_with(value="content")


def test_dispatch_rejects_unpermitted_tool_before_hooks_or_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Role denial short-circuits both middleware and tool execution."""
    handler = MagicMock(return_value="must not run")
    hook_chain = MagicMock()
    registry = ToolRegistry()
    registry.register(_tool("write", handler), roles=[AgentRole.BUILDER])
    monkeypatch.setattr(tools, "_hook_chain", hook_chain)

    result = tools.dispatch(
        _tool_call("write", value="content"),
        _context(AgentRole.REVIEWER),
        registry,
    )

    assert result.startswith("error:")
    assert "write" in result
    handler.assert_not_called()
    hook_chain.run.assert_not_called()


def test_loop_passes_role_filtered_tools_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop advertises only tools available to the active agent role."""
    serialized_tools = [
        {
            "type": "function",
            "function": {
                "name": "inspect",
                "description": "Inspect state.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    registry = MagicMock()
    registry.get_serialized_tools.return_value = serialized_tools
    monkeypatch.setattr(tools, "DEFAULT_REGISTRY", registry)
    chat = MagicMock(
        return_value={
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
        }
    )
    monkeypatch.setattr(loop.provider, "chat", chat)
    messages = [{"role": "user", "content": "inspect"}]
    trace = MagicMock()
    context = _context(AgentRole.INVESTIGATOR)

    result = loop.run(messages, trace, context)

    assert result == "done"
    registry.get_serialized_tools.assert_called_once_with(
        AgentRole.INVESTIGATOR,
    )
    provider_messages, provider_tools = chat.call_args.args
    assert provider_messages is messages
    assert provider_tools == serialized_tools

def test_tools_exports_default_registry() -> None:
    """Callers can import the process-wide default tool registry."""
    assert isinstance(tools.DEFAULT_REGISTRY, ToolRegistry)

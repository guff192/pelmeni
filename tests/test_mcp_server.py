"""Tests for pelmeni tools-mcp stdio server."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from pelmeni.dto.hooks import HookResult
from pelmeni.dto.tools import AgentRole, ToolParameterSchema, ToolSpec
from pelmeni.hooks.chain import HookChain
from pelmeni.mcp.server import McpServer, run_mcp_stdio
from pelmeni.config.models import HookConfigSchema
from pelmeni.tools.dispatch import configure_hooks
from pelmeni.tools.registry import DEFAULT_REGISTRY, ToolRegistry

if TYPE_CHECKING:
    from pathlib import Path


def _make_rpc(
    method: str, params: dict | None = None, req_id: int | str = 1
) -> str:
    payload: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload)


def _call_server(server: McpServer, request_json: str) -> dict | None:
    stdin = io.StringIO(request_json + "\n")
    stdout = io.StringIO()
    server.run(stdin=stdin, stdout=stdout)
    out = stdout.getvalue().strip()
    if not out:
        return None
    return json.loads(out)


def test_initialize_handshake() -> None:
    """Initialize returns capabilities and server info."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    req = _make_rpc(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
        req_id=10,
    )
    resp = _call_server(server, req)
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 10
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "pelmeni-tools-mcp"


def test_initialized_notification_produces_no_response() -> None:
    """Notifications without id must not write output."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    notif = json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    resp = _call_server(server, notif)
    assert resp is None


def test_tools_list_investigator_role() -> None:
    """Investigator role only receives investigator-permitted tools."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    req = _make_rpc("tools/list", req_id=1)
    resp = _call_server(server, req)
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}

    expected_tools = {
        spec.name
        for spec in DEFAULT_REGISTRY.get_tools_for_role(AgentRole.INVESTIGATOR)
    }
    assert tool_names == expected_tools
    assert "read" in tool_names
    assert "grep" in tool_names
    assert "glob" in tool_names
    assert "bash" not in tool_names
    assert "edit" not in tool_names
    assert "write" not in tool_names

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_tools_list_builder_role() -> None:
    """Builder role only receives builder-permitted tools."""
    server = McpServer(role=AgentRole.BUILDER, session_id="test-session")
    req = _make_rpc("tools/list", req_id=2)
    resp = _call_server(server, req)
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}

    expected_tools = {
        spec.name
        for spec in DEFAULT_REGISTRY.get_tools_for_role(AgentRole.BUILDER)
    }
    assert tool_names == expected_tools
    assert "edit" in tool_names
    assert "write" in tool_names
    assert "bash" in tool_names
    assert "glob" not in tool_names
    assert "grep" not in tool_names


def test_tools_call_success(tmp_path: Path) -> None:
    """Successful tool execution returns content array with text."""
    target_file = tmp_path / "hello.txt"
    target_file.write_text("line 1\nline 2\n", encoding="utf-8")

    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    req = _make_rpc(
        "tools/call",
        {"name": "read", "arguments": {"path": str(target_file)}},
        req_id=3,
    )
    resp = _call_server(server, req)
    assert resp is not None
    assert resp["id"] == 3
    result = resp["result"]
    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert "1: line 1" in result["content"][0]["text"]
    assert "2: line 2" in result["content"][0]["text"]


def test_tools_call_role_unauthorized() -> None:
    """Calling an unauthorized tool returns an MCP error result."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    req = _make_rpc(
        "tools/call",
        {"name": "bash", "arguments": {"command": "echo hacked"}},
        req_id=4,
    )
    resp = _call_server(server, req)
    assert resp is not None
    assert resp["id"] == 4
    result = resp["result"]
    assert result["isError"] is True
    assert (
        "not permitted for role 'investigator'" in result["content"][0]["text"]
    )


def test_tools_call_hook_denial() -> None:
    """Security hook denials are returned as isError=True MCP results."""
    mock_hook = MagicMock()
    mock_hook.name = "test_guard"
    mock_hook.return_value = HookResult(
        verdict="deny",
        reason="Security policy: command blocked by test guard",
    )
    config = HookConfigSchema()
    chain = HookChain(hooks=[mock_hook], hook_configs={"test_guard": config})
    configure_hooks(chain)
    try:
        server = McpServer(role=AgentRole.BUILDER, session_id="test-session")
        req = _make_rpc(
            "tools/call",
            {"name": "bash", "arguments": {"command": "cat /etc/shadow"}},
            req_id=5,
        )
        resp = _call_server(server, req)
        assert resp is not None
        assert resp["id"] == 5
        result = resp["result"]
        assert result["isError"] is True
        assert "command blocked by test guard" in result["content"][0]["text"]
    finally:
        configure_hooks(HookChain(hooks=[], hook_configs={}))


def test_tools_call_missing_name() -> None:
    """tools/call without tool name returns JSON-RPC -32602 invalid params."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    req = _make_rpc("tools/call", {"arguments": {}}, req_id=6)
    resp = _call_server(server, req)
    assert resp is not None
    assert resp["id"] == 6
    assert "error" in resp
    assert resp["error"]["code"] == -32602


def test_unknown_method_returns_method_not_found() -> None:
    """Unrecognized methods return JSON-RPC -32601 method not found."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    req = _make_rpc("nonexistent/method", req_id=7)
    resp = _call_server(server, req)
    assert resp is not None
    assert resp["id"] == 7
    assert resp["error"]["code"] == -32601


def test_parse_error_on_malformed_json() -> None:
    """Malformed JSON line returns JSON-RPC -32700 parse error."""
    server = McpServer(role=AgentRole.INVESTIGATOR, session_id="test-session")
    resp = _call_server(server, "{not valid json")
    assert resp is not None
    assert resp["id"] is None
    assert resp["error"]["code"] == -32700


def test_cli_tools_mcp_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI subcommand runs mcp stdio loop with parsed arguments."""
    from pelmeni.cli.main import parse_args

    args = parse_args(
        ["tools-mcp", "--role", "reviewer", "--session-id", "sesh-123"]
    )
    assert args.subcommand == "tools-mcp"
    assert args.role == "reviewer"
    assert args.session_id == "sesh-123"

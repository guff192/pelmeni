"""Model Context Protocol stdio server implementation."""

from __future__ import annotations

import contextlib
import json
import sys
from typing import TYPE_CHECKING, TextIO

from pelmeni.dto.hooks import HookContext
from pelmeni.dto.tools import AgentRole
from pelmeni.tools.dispatch import dispatch
from pelmeni.tools.registry import DEFAULT_REGISTRY, ToolRegistry

if TYPE_CHECKING:
    from pelmeni.dto.tools import ToolSpec

RequestId = str | int | None
CallArgs = dict[str, object]
ValidatedParams = tuple[str, CallArgs] | CallArgs

_ID_KEY = "id"
_NAME_KEY = "name"
_RESULT_KEY = "result"
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "pelmeni-tools-mcp"
_SERVER_VERSION = "0.1.0"


def _format_error(
    req_id: RequestId,
    code: int,
    message: str,
    extra_data: object = None,
) -> dict[str, object]:
    error_payload: dict[str, object] = {"code": code, "message": message}
    if extra_data is not None:
        error_payload["data"] = extra_data
    return {"jsonrpc": "2.0", _ID_KEY: req_id, "error": error_payload}


def _format_result(
    req_id: RequestId,
    res: dict[str, object],
) -> dict[str, object]:
    return {"jsonrpc": "2.0", _ID_KEY: req_id, _RESULT_KEY: res}


def _spec_to_mcp_tool(spec: ToolSpec) -> dict[str, object]:
    """Convert ToolSpec to an MCP tool listing item."""
    return {
        _NAME_KEY: spec.name,
        "description": spec.description,
        "inputSchema": spec.parameters.model_dump(),
    }


def _build_init_response(req_id: str | int) -> dict[str, object]:
    return _format_result(
        req_id,
        {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                _NAME_KEY: _SERVER_NAME,
                "version": _SERVER_VERSION,
            },
        },
    )


def _validate_call_params(
    req_id: str | int,
    call_params: object,
) -> ValidatedParams:
    if not isinstance(call_params, dict):
        return _format_error(
            req_id,
            _INVALID_PARAMS,
            "Invalid params: must be an object",
        )
    tool_name = call_params.get(_NAME_KEY)
    if not isinstance(tool_name, str) or not tool_name:
        return _format_error(
            req_id,
            _INVALID_PARAMS,
            "Invalid params: 'name' is required",
        )
    raw_args = call_params.get("arguments")
    if raw_args is None:
        return tool_name, {}
    if not isinstance(raw_args, dict):
        return _format_error(
            req_id,
            _INVALID_PARAMS,
            "Invalid params: 'arguments' must be an object",
        )
    return tool_name, raw_args


class McpServer:
    """Lightweight stdio MCP server scoping tools to an agent role."""

    def __init__(
        self,
        role: AgentRole | str,
        session_id: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.role = AgentRole(role) if isinstance(role, str) else role
        self.session_id = session_id or "mcp-session"
        self.registry = registry or DEFAULT_REGISTRY
        self._initialized = False

    def handle_request(
        self,
        message: dict[str, object],
    ) -> dict[str, object] | None:
        """Process a single JSON-RPC message."""
        req_id = message.get(_ID_KEY)
        method = message.get("method")

        if not isinstance(method, str):
            if req_id is not None and isinstance(req_id, (str, int)):
                return _format_error(
                    req_id,
                    _INVALID_REQUEST,
                    "Invalid request: missing method",
                )
            return None

        # Notifications (no id)
        if req_id is None or not isinstance(req_id, (str, int)):
            if method == "notifications/initialized":
                self._initialized = True
            return None

        return self._dispatch_method(req_id, method, message.get("params"))

    def run(
        self,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        """Run stdio loop until EOF."""
        in_stream = stdin or sys.stdin
        out_stream = stdout or sys.stdout

        for line in in_stream:
            self._process_stream_line(line.strip(), out_stream)

    def _process_stream_line(self, line: str, out: TextIO) -> None:
        if not line:
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            err = _format_error(None, _PARSE_ERROR, f"Parse error: {exc}")
            out.write(f"{json.dumps(err)}\n")
            out.flush()
            return

        if not isinstance(message, dict):
            msg = "Invalid request: message must be an object"
            err = _format_error(None, _INVALID_REQUEST, msg)
            out.write(f"{json.dumps(err)}\n")
            out.flush()
            return

        response = self.handle_request(message)
        if response is not None:
            out.write(f"{json.dumps(response)}\n")
            out.flush()

    def _dispatch_method(
        self,
        req_id: str | int,
        method: str,
        call_params: object,
    ) -> dict[str, object]:
        if method == "initialize":
            return _build_init_response(req_id)
        if method == "tools/list":
            return self._handle_tools_list(req_id)
        if method == "tools/call":
            return self._handle_tools_call(req_id, call_params)
        if method == "ping":
            return _format_result(req_id, {})
        return _format_error(
            req_id,
            _METHOD_NOT_FOUND,
            f"Method not found: {method}",
        )

    def _handle_tools_list(self, req_id: str | int) -> dict[str, object]:
        available_tools = [
            _spec_to_mcp_tool(spec)
            for spec in self.registry.get_tools_for_role(self.role)
        ]
        return _format_result(req_id, {"tools": available_tools})

    def _handle_tools_call(
        self,
        req_id: str | int,
        call_params: object,
    ) -> dict[str, object]:
        validated = _validate_call_params(req_id, call_params)
        if isinstance(validated, dict):
            return validated

        call_dict = {
            _ID_KEY: str(req_id),
            "type": "function",
            "function": {
                _NAME_KEY: validated[0],
                "arguments": json.dumps(validated[1]),
            },
        }
        with contextlib.redirect_stdout(sys.stderr):
            out_str = dispatch(
                call_dict,
                context=HookContext(
                    agent_role=self.role, session_id=self.session_id
                ),
                registry=self.registry,
            )
        return _format_result(
            req_id,
            {
                "content": [{"type": "text", "text": out_str}],
                "isError": out_str.startswith(("error:", "Security policy:")),
            },
        )


def run_mcp_stdio(
    role: AgentRole | str,
    session_id: str | None = None,
) -> None:
    """Entry point for pelmeni tools-mcp command."""
    server = McpServer(role=role, session_id=session_id)
    server.run()

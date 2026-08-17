# flake8: noqa: WPS226, WPS204
# WPS226 & WPS204 (string literal & expression overuse) suppressed for this
# file to keep JSON / OpenAI tool schema definitions clean and readable
# without creating bloat constants (e.g. "type", "function", "string").
"""Tool schema definitions, registry, dispatch, and execution."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

from pelmeni.dto.tools import (
    AgentRole,
    Tool,
    ToolFunction,
    ToolParameterSchema,
    ToolSpec,
)

if TYPE_CHECKING:
    from pelmeni.dto.hooks import HookContext
    from pelmeni.hooks.chain import HookChain


class ToolRegistry:
    """Store tool specifications and role-specific access permissions."""

    def __init__(self) -> None:
        """Initialize an empty registry for every supported role."""
        self._tools: dict[str, ToolSpec] = {}
        self._whitelists: dict[AgentRole, set[str]] = {
            role: set() for role in AgentRole
        }

    def register(
        self,
        tool: ToolSpec,
        roles: list[AgentRole] | None = None,
    ) -> None:
        """Register a tool and grant it to the selected roles."""
        self._tools[tool.name] = tool
        for whitelist in self._whitelists.values():
            whitelist.discard(tool.name)
        granted_roles = list(AgentRole) if roles is None else roles
        for role in granted_roles:
            self._whitelists[role].add(tool.name)

    def get_tools_for_role(self, role: AgentRole) -> list[ToolSpec]:
        """Return allowed tools in registration order."""
        whitelist = self._whitelists[role]
        return [
            tool
            for name, tool in self._tools.items()
            if name in whitelist
        ]

    def is_tool_allowed(self, role: AgentRole | str, tool_name: str) -> bool:
        """Return whether a registered tool is available to a role."""
        try:
            resolved_role = AgentRole(role)
        except ValueError:
            return False
        return (
            tool_name in self._tools
            and tool_name in self._whitelists.get(resolved_role, set())
        )

    def get_serialized_tools(
        self,
        role: AgentRole | str,
    ) -> list[dict[str, Any]]:
        """Serialize a role's allowed tools for provider function calling."""
        resolved_role = AgentRole(role)
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters.model_dump(),
                },
            }
            for tool in self.get_tools_for_role(resolved_role)
        ]


BASH_TOOL = Tool(
    type="function",
    function=ToolFunction(
        name="bash",
        description=(
            "Run a shell command and return stdout, stderr, and exit code. "
            "Use for file inspection, searching, and running programs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                }
            },
            "required": ["command"],
        },
    ),
)

TOOLS = (BASH_TOOL,)

# Pre-serialized wire form; TOOLS is static, so dump once at import.
SERIALIZED_TOOLS = tuple(tool.model_dump() for tool in TOOLS)

_TIMEOUT_SECONDS = 60
_MAX_OUTPUT_CHARS = 30_000
_hook_chain: HookChain | None = None


def configure_hooks(chain: HookChain) -> None:
    """Set the hook chain used by dispatch."""
    globals()["_hook_chain"] = chain


def execute_bash(command: str) -> str:
    """Run a command, return a plain-text result for the tool message."""
    try:
        # shell=True is intentional — the bash tool's contract is raw shell
        # access for agents; governance belongs to the hook middleware,
        # not to crippling the tool with shell=False.
        proc = subprocess.run(  # noqa: S602
            command,
            check=False,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {_TIMEOUT_SECONDS}s"
    except subprocess.CalledProcessError as exc:
        return f"error: command finished with return code {exc.returncode}"

    out_parts = [f"$ {command}\n"]
    if proc.stdout:
        out_parts.append(proc.stdout)
    if proc.stderr:
        out_parts.append(f"\n[stderr]\n{proc.stderr}")
    out_parts.append(f"\n[exit code: {proc.returncode}]")
    out = "".join(out_parts)
    if len(out) > _MAX_OUTPUT_CHARS:
        truncated = out[:_MAX_OUTPUT_CHARS]
        out = f"{truncated}\n[output truncated]"
    return out


def _standard_tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    handler: Any = None,  # noqa: ANN401
) -> ToolSpec:
    """Build one standard tool specification."""
    return ToolSpec(
        name=name,
        description=description,
        parameters=ToolParameterSchema(
            properties=properties,
            required=required,
        ),
        handler=handler,
    )


def _build_default_registry() -> ToolRegistry:
    """Create the process-wide registry with role-specific permissions."""
    registry = ToolRegistry()
    path_property = {"path": {"type": "string"}}
    standard_tools = {
        "bash": _standard_tool(
            "bash",
            "Run a shell command and return its output.",
            {"command": {"type": "string"}},
            ["command"],
            execute_bash,
        ),
        "read": _standard_tool(
            "read", "Read a file or directory.", path_property, ["path"],
        ),
        "grep": _standard_tool(
            "grep",
            "Search files for a regular expression.",
            {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            ["pattern", "path"],
        ),
        "glob": _standard_tool(
            "glob",
            "Find paths matching a glob pattern.",
            path_property,
            ["path"],
        ),
        "lsp": _standard_tool(
            "lsp",
            "Query language-server information.",
            {
                "operation": {"type": "string"},
                "path": {"type": "string"},
            },
            ["operation", "path"],
        ),
        "edit": _standard_tool(
            "edit",
            "Apply a surgical edit to an existing file.",
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
        ),
        "write": _standard_tool(
            "write",
            "Create or overwrite a file.",
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
        ),
    }
    role_tools = {
        AgentRole.INVESTIGATOR: ("grep", "glob", "lsp", "read"),
        AgentRole.BUILDER: ("read", "edit", "write", "bash"),
        AgentRole.REVIEWER: ("read", "grep", "lsp", "bash"),
        AgentRole.TESTER: ("bash", "write", "read"),
    }
    for name, tool in standard_tools.items():
        roles = [
            role
            for role, allowed_names in role_tools.items()
            if name in allowed_names
        ]
        registry.register(tool, roles=roles)
    return registry


DEFAULT_REGISTRY: ToolRegistry = _build_default_registry()


def _run_hooks(tool_call: dict, context: HookContext) -> dict | str:
    if _hook_chain is None:
        return tool_call
    hook_result = _hook_chain.run(tool_call, context)
    if hook_result.verdict == "deny":
        return f"error: blocked by hook: {hook_result.reason}"
    if hook_result.verdict == "modify" and hook_result.tool_call is not None:
        return hook_result.tool_call
    return tool_call


def dispatch(
    tool_call: dict[str, Any],
    context: HookContext,
    registry: ToolRegistry | None = None,
) -> str:
    """Execute one permitted tool call from the model. Never raises."""
    active_registry = DEFAULT_REGISTRY if registry is None else registry
    tool_name = tool_call["function"]["name"]
    if not active_registry.is_tool_allowed(context.agent_role, tool_name):
        return (
            f"error: Tool '{tool_name}' is not permitted for role "
            f"'{context.agent_role}'."
        )

    processed_call = _run_hooks(tool_call, context)
    if isinstance(processed_call, str):
        return processed_call
    name = processed_call["function"]["name"]
    try:
        arguments = json.loads(
            processed_call["function"]["arguments"] or "{}",
        )
    except json.JSONDecodeError as exc:
        return f"error: malformed tool arguments: {exc}"

    spec = active_registry._tools.get(name)  # noqa: SLF001
    if spec is None or spec.handler is None:
        return f"error: unknown tool '{name}'"
    try:
        tool_result = spec.handler(**arguments)
    except (TypeError, ValueError) as exc:
        return f"error: invalid tool arguments: {exc}"
    if name == "bash":
        print(f"\n── bash ──\n{tool_result}\n")
    return str(tool_result)

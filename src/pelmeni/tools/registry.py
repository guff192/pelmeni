# flake8: noqa: WPS226, WPS204
"""Tool specifications, registry, and default registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pelmeni.dto.tools import (
    AgentRole,
    Tool,
    ToolFunction,
    ToolParameterSchema,
    ToolSpec,
)
from pelmeni.tools.bash import execute_bash
from pelmeni.tools.file_ops import edit_file, read_path, write_file
from pelmeni.tools.search import glob_paths, grep_search

if TYPE_CHECKING:
    from collections.abc import Sequence


class ToolRegistry:
    """Store tool specifications and role-specific access permissions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._whitelists: dict[str, set[str]] = {
            role.value: set() for role in AgentRole
        }

    def register(
        self,
        tool: ToolSpec,
        roles: Sequence[AgentRole | str] = (),
    ) -> None:
        """Register a tool specification and grant access to roles."""
        self._tools[tool.name] = tool
        for role in roles:
            role_key = role.value if isinstance(role, AgentRole) else str(role)
            self._whitelists.setdefault(role_key, set()).add(tool.name)

    def get_tools_for_role(self, role: AgentRole | str) -> list[ToolSpec]:
        """Return all tool specifications permitted for a role."""
        role_key = role.value if isinstance(role, AgentRole) else str(role)
        allowed_names = self._whitelists.get(role_key, set())
        matching: list[ToolSpec] = []
        for name, tool in self._tools.items():
            if name in allowed_names:
                matching.append(tool)
        return matching

    def is_tool_allowed(self, role: AgentRole | str, tool_name: str) -> bool:
        """Check whether a tool name is permitted for a given role."""
        role_key = role.value if isinstance(role, AgentRole) else str(role)
        allowed = self._whitelists.get(role_key)
        if allowed is None:
            return False
        return tool_name in allowed

    def get_serialized_tools(
        self,
        role: AgentRole | str,
    ) -> list[dict[str, Any]]:
        """Return provider-format function tool schemas for permitted tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters.model_dump(),
                },
            }
            for tool in self.get_tools_for_role(role)
        ]


BASH_TOOL = Tool(
    type="function",
    function=ToolFunction(
        name="bash",
        description="Run a shell command and return its output.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to run",
                },
            },
            "required": ["command"],
        },
    ),
)

TOOLS = (BASH_TOOL,)
SERIALIZED_TOOLS = tuple(tool.model_dump() for tool in TOOLS)


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
    standard_tools = {
        "bash": _standard_tool(
            "bash",
            "Run a shell command and return its output.",
            {"command": {"type": "string"}},
            ["command"],
            execute_bash,
        ),
        "read": _standard_tool(
            "read",
            "Read a file or directory.",
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            ["path"],
            read_path,
        ),
        "grep": _standard_tool(
            "grep",
            "Search files for a regular expression.",
            {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            },
            ["pattern"],
            grep_search,
        ),
        "glob": _standard_tool(
            "glob",
            "Find paths matching a glob pattern.",
            {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            ["pattern"],
            glob_paths,
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
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            ["path", "old_text", "new_text"],
            edit_file,
        ),
        "write": _standard_tool(
            "write",
            "Create or overwrite a file.",
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
            write_file,
        ),
    }
    role_tools = {
        AgentRole.INVESTIGATOR: ("grep", "glob", "lsp", "read"),
        AgentRole.BUILDER: ("read", "edit", "write", "bash"),
        AgentRole.REVIEWER: ("read", "grep", "lsp", "bash"),
        AgentRole.TESTER: ("bash", "write", "read"),
    }
    for name, tool in standard_tools.items():
        roles: list[AgentRole] = []
        for role, allowed_names in role_tools.items():
            if name in allowed_names:
                roles.append(role)
        registry.register(tool, roles=roles)
    return registry


DEFAULT_REGISTRY: ToolRegistry = _build_default_registry()

"""Bash tool schema, dispatch, and execution."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from pelmeni.dto.tools import AgentRole, Tool, ToolFunction, ToolSpec

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

    def is_tool_allowed(self, role: AgentRole, tool_name: str) -> bool:
        """Return whether a registered tool is available to a role."""
        return (
            tool_name in self._tools
            and tool_name in self._whitelists[role]
        )


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
)  # noqa: WPS226

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
        # TODO: replace raw shell=True with hook-gated two-tier tool (step 3):
        # safe `run` (shlex.split, no shell) + `bash` (shell, hook-gated).
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


def _run_hooks(tool_call: dict, context: HookContext) -> dict | str:
    if _hook_chain is None:
        return tool_call
    hook_result = _hook_chain.run(tool_call, context)
    if hook_result.verdict == "deny":
        return f"error: blocked by hook: {hook_result.reason}"
    if hook_result.verdict == "modify" and hook_result.tool_call is not None:
        return hook_result.tool_call
    return tool_call


def dispatch(tool_call: dict, context: HookContext) -> str:
    """Execute one tool call from the model. Never raises."""
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

    if name == "bash":
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return "error: missing or empty 'command' argument"
        tool_result = execute_bash(command)
        print(f"\n── bash ──\n{tool_result}\n")
        return tool_result
    return f"error: unknown tool '{name}'"

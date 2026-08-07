"""Bash tool: schema, dispatch, and a minimal hardcoded guard.

Step-1 scope: the only tool is `bash`. The blocklist below is a temporary
guard — the customizable hook middleware replaces it in build step 3.
"""

import json
import re
import subprocess
import types

BASH_TOOL = types.MappingProxyType(
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a shell command and return stdout, stderr, and exit code. "
                "Use for file inspection, searching, and running programs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    }
)

TOOLS = (BASH_TOOL,)

_TIMEOUT_SECONDS = 60
_MAX_OUTPUT_CHARS = 30_000

# Temporary guard; replaced by hook middleware in step 3.
_BLOCKED = (
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+/\s*$"),
    re.compile(r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r?\s+/\s*$"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\b.*\bof=/dev/"),
    re.compile(r":\(\)\{.*\}"),  # fork bomb
)


def execute_bash(command: str) -> str:
    """Run a command, return a plain-text result for the tool message."""
    if any(pattern.search(command) for pattern in _BLOCKED):
        return "error: command blocked by safety guard"

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
        out = f"{out[:_MAX_OUTPUT_CHARS]}\n[output truncated]"
    return out


def dispatch(tool_call: dict) -> str:
    """Execute one tool call from the model. Never raises."""
    name = tool_call["function"]["name"]
    try:
        args = json.loads(tool_call["function"]["arguments"] or "{}")
    except json.JSONDecodeError as exc:
        return f"error: malformed tool arguments: {exc}"

    if name == "bash":
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return "error: missing or empty 'command' argument"
        tool_result = execute_bash(command)
        print(f"\n── bash ──\n{tool_result}\n")
        return tool_result
    return f"error: unknown tool '{name}'"

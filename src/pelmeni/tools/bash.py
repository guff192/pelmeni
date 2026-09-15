"""Bash shell execution handler with timeout and output bounds."""

from __future__ import annotations

import subprocess

_MAX_OUTPUT_CHARS = 30_000
_TIMEOUT_SECONDS = 60


def execute_bash(command: str) -> str:
    """Run a command, return a plain-text result for the tool message."""
    try:
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
    out = (proc.stdout + proc.stderr).strip()
    if not out:
        out = "(command produced no output)"
    if len(out) > _MAX_OUTPUT_CHARS:
        truncated = out[:_MAX_OUTPUT_CHARS]
        out = f"{truncated}\n[output truncated]"
    return out

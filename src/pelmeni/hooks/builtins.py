"""Built-in tool call hooks."""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Literal

from pelmeni.dto.hooks import HookResult

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pelmeni.dto.hooks import HookContext

_BLOCKLIST_PATTERNS = (
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+/\s*$",
    r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r?\s+/\s*$",
    r"\bmkfs\b",
    r"\bdd\b.*\bof=/dev/",
    r":\(\)\{.*\}",
)
_PATH_KEYS = ("path", "file", "target")
_ALLOW: Literal["allow"] = "allow"
_DENY: Literal["deny"] = "deny"


class BlocklistHook:
    """Deny shell commands matching known destructive patterns."""

    name = "blocklist"

    def __init__(self) -> None:
        self._patterns = tuple(
            re.compile(pattern) for pattern in _BLOCKLIST_PATTERNS
        )

    def __call__(
        self,
        tool_call: dict,
        context: HookContext,  # noqa: ARG002
    ) -> HookResult:
        """Inspect a command and deny known destructive forms."""
        arguments = _parse_arguments(tool_call)
        command = arguments.get("command")
        if not isinstance(command, str):
            return HookResult(verdict=_ALLOW)
        for pattern in self._patterns:
            if pattern.search(command):
                return HookResult(
                    verdict=_DENY,
                    reason=f"blocked: {pattern.pattern}",
                )
        return HookResult(verdict=_ALLOW)


class PathGuardHook:
    """Restrict path-oriented tool calls to configured glob patterns."""

    name = "path_guard"

    def __init__(
        self,
        allow: Sequence[str] = ("./**",),
        deny: Sequence[str] = ("/etc/**", "/usr/**", "~/.ssh/**"),
    ) -> None:
        self._allow = tuple(allow)
        self._deny = tuple(deny)

    def __call__(
        self,
        tool_call: dict,
        context: HookContext,  # noqa: ARG002
    ) -> HookResult:
        """Deny paths outside the configured allow patterns."""
        if tool_call.get("function", {}).get("name") == "bash":
            return HookResult(verdict=_ALLOW)
        arguments = _parse_arguments(tool_call)
        paths = _extract_paths(arguments)
        for path in paths:
            path_verdict = self._check_path(path)
            if path_verdict is not None:
                return path_verdict
        return HookResult(verdict=_ALLOW)

    def _check_path(self, path: str) -> HookResult | None:
        if any(fnmatch(path, pattern) for pattern in self._deny):
            return HookResult(
                verdict=_DENY,
                reason=f"path denied: {path}",
            )
        if not any(fnmatch(path, pattern) for pattern in self._allow):
            return HookResult(
                verdict=_DENY,
                reason=f"path not allowed: {path}",
            )
        return None


class ConfirmPromptHook:
    """Require confirmation before a tool call is allowed."""

    name = "confirm_prompt"

    def __init__(
        self,
        mode: str = "ask",
        confirm_fn: Callable[[str], bool] | None = None,
    ) -> None:
        self._mode = mode
        self._confirm_fn = confirm_fn or _stdin_confirm

    def __call__(
        self,
        tool_call: dict,
        context: HookContext,  # noqa: ARG002
    ) -> HookResult:
        """Apply the configured confirmation policy."""
        if self._mode == "always-allow":
            return HookResult(verdict=_ALLOW)
        if self._mode == "always-deny":
            return HookResult(
                verdict=_DENY,
                reason="confirm_prompt auto-deny",
            )
        summary = json.dumps(tool_call, indent=2, sort_keys=True)
        if self._confirm_fn(summary):
            return HookResult(verdict=_ALLOW)
        return HookResult(
            verdict=_DENY,
            reason="confirm_prompt rejected",
        )


def _parse_arguments(tool_call: dict) -> dict:
    raw_arguments = tool_call.get("function", {}).get("arguments", "")
    if not isinstance(raw_arguments, str):
        return {}
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return arguments if isinstance(arguments, dict) else {}


def _extract_paths(arguments: dict) -> tuple[str, ...]:
    return tuple(
        user_input
        for key in _PATH_KEYS
        if isinstance((user_input := arguments.get(key)), str)
    )


def _stdin_confirm(summary: str) -> bool:
    print(summary)
    try:
        answer = input("Allow? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.lower() in {"y", "yes"}

"""Data transfer objects for hook middleware."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class HookContext:
    """Immutable context passed to every hook invocation."""

    agent_role: str
    session_id: str
    tool_history: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HookResult:
    """Verdict returned by a hook."""

    verdict: Literal["allow", "deny", "modify"]
    tool_call: dict[str, Any] | None = None
    reason: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

"""Data transfer objects for hook middleware."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pelmeni.hooks.chain import HookChain
    from pelmeni.tools.registry import ToolRegistry


@dataclass(frozen=True)
class HookContext:
    """Immutable context passed to every hook invocation."""

    agent_role: str
    session_id: str
    tool_history: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecutionContext:
    """Execution context containing hook context, registry, and hook chain."""

    hook_context: HookContext
    registry: ToolRegistry
    hook_chain: HookChain | None = None


@dataclass(frozen=True)
class HookResult:
    """Verdict returned by a hook."""

    verdict: Literal["allow", "deny", "modify"]
    tool_call: dict[str, Any] | None = None
    reason: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

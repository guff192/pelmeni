"""Hook protocol for tool call middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pelmeni.dto.hooks import HookContext, HookResult


@runtime_checkable
class Hook(Protocol):
    """Interface every hook must satisfy."""

    name: str

    def __call__(
        self,
        tool_call: dict,
        context: HookContext,
    ) -> HookResult:
        """Inspect or transform a tool call."""
        ...

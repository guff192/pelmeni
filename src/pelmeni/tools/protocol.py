"""Protocol definitions for tool registry and access control."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pelmeni.dto.tools import AgentRole


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Protocol for checking tool access permissions."""

    def is_tool_allowed(self, role: AgentRole | str, tool_name: str) -> bool:
        """Check whether a tool name is permitted for a role."""
        ...

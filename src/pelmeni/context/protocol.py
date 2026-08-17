"""Context protocol definitions.

Defines runtime-checkable protocols used by the context compaction system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pelmeni.dto.context import (
        CompactionConfigSchema,
        CompactionResult,
    )


@runtime_checkable
class TokenEstimator(Protocol):
    """Protocol for estimating message token counts."""

    def estimate_message(self, message: dict[str, Any]) -> int:
        """Estimate token count for a single message."""
        ...

    def estimate_messages(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total token count for a sequence of messages."""
        ...


@runtime_checkable
class ContextCompactor(Protocol):
    """Protocol for message context compaction engines."""

    def compact(
        self,
        messages: list[dict[str, Any]],
        config: CompactionConfigSchema,
    ) -> CompactionResult:
        """Condense message history according to compaction configuration."""
        ...

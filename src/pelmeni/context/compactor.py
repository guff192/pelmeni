"""Truncate compactor for Pelmeni context.

The compactor drops older messages when token usage exceeds the target. It
operates using a simple heuristic token estimator (character count of the JSON
representation) and respects the configuration options defined in
``pelmeni.dto.context.CompactionConfigSchema``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pelmeni.context.estimator import get_default_estimator
from pelmeni.dto.context import (
    CompactionConfigSchema,
    CompactionResult,
    CompactionStrategy,
)

if TYPE_CHECKING:
    from pelmeni.context.protocol import ContextCompactor, TokenEstimator


class TruncateCompactor:
    """Compact message history by truncating oldest entries.

    The algorithm is straightforward:

    1. If ``config.enabled`` is ``False`` the original message list is returned
       unchanged.
    2. The total token count is estimated via the supplied ``estimator``.
    3. If the count exceeds ``config.max_tokens`` the algorithm removes the
       oldest non-system messages until the count falls to or below
       ``config.target_tokens``, while keeping at least
       ``config.keep_recent_rounds`` messages.
    4. The system message at index 0 is never pruned.
    5. A :class:`CompactionResult` describing the operation is returned.
    """

    def __init__(self, estimator: TokenEstimator) -> None:
        """Initialise with a token estimator."""
        self._estimator = estimator

    def compact(  # noqa: WPS210
        self,
        messages: list[dict[str, Any]],
        config: CompactionConfigSchema,
    ) -> CompactionResult:
        """Return a possibly shortened list of ``messages``.

        Parameters
        ----------
        messages:
            The full message history.
        config:
            Compaction configuration governing behaviour.

        """
        tokens_before = self._estimator.estimate_messages(messages)

        if not config.enabled:
            return CompactionResult(
                compacted=False,
                original_count=len(messages),
                compacted_count=len(messages),
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                messages=messages,
                strategy_used=CompactionStrategy.TRUNCATE,
            )

        if tokens_before <= config.max_tokens:
            return CompactionResult(
                compacted=False,
                original_count=len(messages),
                compacted_count=len(messages),
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                messages=messages,
                strategy_used=CompactionStrategy.TRUNCATE,
            )

        keep = max(config.keep_recent_rounds, 0)
        truncated: list[dict[str, Any]] = list(messages)
        running_tokens = tokens_before

        while running_tokens > config.target_tokens and len(truncated) > keep:
            freed = self._prune_oldest_turn(truncated)
            if freed <= 0:
                break
            running_tokens -= freed

        return CompactionResult(
            compacted=True,
            original_count=len(messages),
            compacted_count=len(truncated),
            tokens_before=tokens_before,
            tokens_after=running_tokens,
            messages=truncated,
            strategy_used=CompactionStrategy.TRUNCATE,
        )

    def _prune_oldest_turn(self, truncated: list[dict[str, Any]]) -> int:
        """Prune oldest non-system message and any paired tool outputs."""
        pop_index = int(
            bool(truncated and truncated[0].get("role") == "system"),
        )
        if pop_index >= len(truncated):
            return 0
        removed = truncated.pop(pop_index)
        freed_tokens = self._estimator.estimate_message(removed)
        if removed.get("role") == "assistant" and removed.get("tool_calls"):
            call_ids = {
                tool_call.get("id")
                for tool_call in removed.get("tool_calls", [])
            }
            while pop_index < len(truncated):
                if truncated[pop_index].get("role") != "tool":
                    break
                if truncated[pop_index].get("tool_call_id") not in call_ids:
                    break
                tool_msg = truncated.pop(pop_index)
                freed_tokens += self._estimator.estimate_message(tool_msg)
        return freed_tokens


def get_default_compactor() -> ContextCompactor:
    """Factory returning a default :class:`ContextCompactor` implementation.

    The default uses the heuristic token estimator defined in
    ``pelmeni.context.estimator``.
    """
    return TruncateCompactor(get_default_estimator())

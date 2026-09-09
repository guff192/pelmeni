"""Truncate compactor for Pelmeni context.

The compactor drops older messages when token usage exceeds the target. It
operates using a simple heuristic token estimator (character count of the JSON
representation) and respects the configuration options defined in
``pelmeni.dto.context.CompactionConfigSchema``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pelmeni.context.estimator import get_default_estimator
from pelmeni.domain.rounds import group_into_rounds
from pelmeni.dto.context import (
    CompactionConfigSchema,
    CompactionResult,
    CompactionStrategy,
)

if TYPE_CHECKING:
    from pelmeni.context.protocol import ContextCompactor, TokenEstimator
    from pelmeni.domain.messages import Message, SystemMessage
    from pelmeni.domain.rounds import Round


class TruncateCompactor:
    """Compact message history by truncating oldest entries.

    The algorithm is straightforward:

    1. If ``config.enabled`` is ``False`` the original message list is returned
       unchanged.
    2. The total token count is estimated via the supplied ``estimator``.
    3. If the count exceeds ``config.max_tokens`` the algorithm removes the
       oldest non-system rounds until the count falls to or below
       ``config.target_tokens``, while keeping at least
       ``config.keep_recent_rounds`` rounds.
    4. The system message at index 0 is never pruned.
    5. A :class:`CompactionResult` describing the operation is returned.
    """

    def __init__(self, estimator: TokenEstimator) -> None:
        """Initialise with a token estimator."""
        self._estimator = estimator

    def compact(
        self,
        messages: list[Message],
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

        system, rounds = group_into_rounds(messages)
        keep = max(config.keep_recent_rounds, 0)
        running_tokens = tokens_before

        while running_tokens > config.target_tokens and len(rounds) > keep:
            freed = self._prune_oldest_round(rounds)
            if freed <= 0:
                break
            running_tokens -= freed

        truncated = self._flatten(system, rounds)
        return CompactionResult(
            compacted=True,
            original_count=len(messages),
            compacted_count=len(truncated),
            tokens_before=tokens_before,
            tokens_after=running_tokens,
            messages=truncated,
            strategy_used=CompactionStrategy.TRUNCATE,
        )

    def _prune_oldest_round(self, rounds: list[Round]) -> int:
        """Remove the oldest round and return freed token count."""
        if not rounds:
            return 0
        oldest = rounds.pop(0)
        return sum(
            self._estimator.estimate_message(msg)
            for msg in oldest.all_messages
        )

    def _flatten(
        self,
        system: SystemMessage | None,
        rounds: list[Round],
    ) -> list[Message]:
        """Re-flatten system message and rounds into a message list."""
        flattened: list[Message] = []
        if system is not None:
            flattened.append(system)
        for rnd in rounds:
            flattened.extend(rnd.all_messages)
        return flattened


def get_default_compactor() -> ContextCompactor:
    """Factory returning a default :class:`ContextCompactor` implementation.

    The compactor can be replaced with a summarisation-based implementation
    without touching call sites.
    """
    return TruncateCompactor(get_default_estimator())

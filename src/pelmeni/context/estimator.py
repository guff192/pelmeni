"""Heuristic token estimator for Pelmeni context.

This simple implementation approximates token counts by using the length of the
JSON-encoded message string. It satisfies the :class:`TokenEstimator` protocol
defined in ``pelmeni.context.protocol``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pelmeni.domain.message_mappers import message_to_dto

if TYPE_CHECKING:
    from pelmeni.context.protocol import TokenEstimator
    from pelmeni.domain.messages import Message


class HeuristicEstimator:
    """Estimate token usage based on message string length.

    The estimator treats each character as roughly one token. While this is a
    crude approximation it is deterministic, fast, and sufficient for the
    proof-of-concept compaction engine used in tests.
    """

    def estimate_message(self, message: Message) -> int:
        """Estimate tokens for a single message."""
        return self._message_len(message)

    def estimate_messages(self, messages: list[Message]) -> int:
        """Estimate tokens for a list of messages."""
        return sum(self._message_len(msg) for msg in messages)

    def _message_len(self, message: Message) -> int:
        """Return a deterministic length for message."""
        return len(
            json.dumps(
                message_to_dto(message),
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )


def get_default_estimator() -> TokenEstimator:
    """Factory returning a default :class:`TokenEstimator` implementation.

    The function exists so the estimator can be swapped out for a more
    sophisticated model-based version without touching call sites.
    """
    return HeuristicEstimator()

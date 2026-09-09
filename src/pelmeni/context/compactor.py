"""Truncate compactor for Pelmeni context.

The compactor drops older messages when token usage exceeds the target. It
operates using a simple heuristic token estimator (character count of the JSON
representation) and respects the configuration options defined in
``pelmeni.dto.context.CompactionConfigSchema``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pelmeni.context.estimator import get_default_estimator
from pelmeni.domain.messages import AssistantMessage, ToolMessage
from pelmeni.domain.rounds import Round, group_into_rounds
from pelmeni.dto.context import (
    CompactionConfigSchema,
    CompactionResult,
    CompactionStrategy,
)

if TYPE_CHECKING:
    from pelmeni.context.protocol import ContextCompactor, TokenEstimator
    from pelmeni.domain.messages import Message, SystemMessage


def _build_truncation_marker(elided: int) -> str:
    return f"\n\n[...truncated {elided} chars...]\n\n"


def truncate_tool_output(raw_text: str, max_chars: int) -> str:
    """Truncate tool output to max_chars with head, marker, and tail."""
    if len(raw_text) <= max_chars:
        return raw_text
    half = max_chars // 2
    tail_index = half - max_chars
    marker = _build_truncation_marker(len(raw_text) - max_chars)
    head = raw_text[:half]
    tail = raw_text[tail_index:]
    return f"{head}{marker}{tail}"


def _condense_round_tools(rnd: Round, max_chars: int) -> Round:
    """Condense oversized ToolMessage turns in a single round."""
    new_turns: list[AssistantMessage | ToolMessage] = []
    for turn in rnd.turns:
        if isinstance(turn, ToolMessage) and len(turn.content) > max_chars:
            new_turns.append(
                replace(
                    turn,
                    content=truncate_tool_output(turn.content, max_chars),
                )
            )
        else:
            new_turns.append(turn)
    return Round(user=rnd.user, turns=tuple(new_turns))


class TruncateCompactor:
    """Compact message history by truncating oldest entries.

    The algorithm operates in two tiers:
    1. If ``config.enabled`` is ``False`` the original messages are returned.
    2. If token count exceeds ``config.max_tokens``:
       a. Historical tool messages in older rounds are condensed.
       b. If token count still exceeds ``config.target_tokens``, oldest rounds
          are pruned while keeping at least ``config.keep_recent_rounds``.
    3. The system message at index 0 is never pruned.
    4. A :class:`CompactionResult` describing the operation is returned.
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

        if not config.enabled or tokens_before <= config.max_tokens:
            return self._no_op_result(messages, tokens_before)

        system, rounds = group_into_rounds(messages)
        rounds = self._condense_historical_rounds(rounds, config.max_tool_chars)
        running_tokens = self._estimator.estimate_messages(
            self._flatten(system, rounds)
        )
        running_tokens = self._prune_rounds_to_target(
            rounds,
            config.target_tokens,
            max(config.keep_recent_rounds, 0),
            running_tokens,
        )
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

    def _no_op_result(
        self,
        messages: list[Message],
        tokens: int,
    ) -> CompactionResult:
        """Return a no-op compaction result when compaction is not needed."""
        return CompactionResult(
            compacted=False,
            original_count=len(messages),
            compacted_count=len(messages),
            tokens_before=tokens,
            tokens_after=tokens,
            messages=messages,
            strategy_used=CompactionStrategy.TRUNCATE,
        )

    def _condense_historical_rounds(
        self,
        rounds: list[Round],
        max_tool_chars: int,
    ) -> list[Round]:
        """Condense historical tool outputs in older rounds."""
        if len(rounds) <= 1:
            return rounds
        condensed = [
            _condense_round_tools(rnd, max_tool_chars) for rnd in rounds[:-1]
        ]
        return [*condensed, rounds[-1]]

    def _prune_rounds_to_target(
        self,
        rounds: list[Round],
        target_tokens: int,
        keep_rounds: int,
        running_tokens: int,
    ) -> int:
        """Prune oldest rounds until token count is within target."""
        tokens = running_tokens
        while tokens > target_tokens and len(rounds) > keep_rounds:
            freed = self._prune_oldest_round(rounds)
            if freed <= 0:
                break
            tokens -= freed
        return tokens

    def _prune_oldest_round(self, rounds: list[Round]) -> int:
        """Remove the oldest round and return freed token count."""
        if not rounds:
            return 0
        oldest = rounds.pop(0)
        return sum(
            self._estimator.estimate_message(msg) for msg in oldest.all_messages
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

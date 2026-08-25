"""Unit and integration tests for the context compaction engine.

Tests cover:
- HeuristicEstimator correctness and edge cases.
- TruncateCompactor logic (disabled, below threshold, above threshold).
- System-message preservation invariant.
- get_default_estimator / get_default_compactor factories.
- loop.run() compaction integration via a stubbed provider.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from pelmeni.context.compactor import TruncateCompactor, get_default_compactor
from pelmeni.context.estimator import HeuristicEstimator, get_default_estimator
from pelmeni.context.protocol import ContextCompactor, TokenEstimator
from pelmeni.dto.context import (
    CompactionConfigSchema,
    CompactionResult,
    CompactionStrategy,
)
from pelmeni.loop import run
from pelmeni.providers.router import ProviderError

# Helpers
# ---------------------------------------------------------------------------

def _msg(role: str, content: str) -> dict[str, Any]:
    """Return a minimal message dict."""
    return {"role": role, "content": content}


def _char_len(message: dict[str, Any]) -> int:
    """Expected length from HeuristicEstimator._message_len."""
    return len(json.dumps(message, separators=(",", ":"), ensure_ascii=False))


# ---------------------------------------------------------------------------
# HeuristicEstimator unit tests
# ---------------------------------------------------------------------------

class TestHeuristicEstimator:
    """Tests for HeuristicEstimator."""

    def test_estimate_message_equals_json_length(self) -> None:
        """estimate_message returns the compact JSON character count."""
        estimator = HeuristicEstimator()
        msg = _msg("user", "hello")
        assert estimator.estimate_message(msg) == _char_len(msg)

    def test_estimate_messages_is_sum(self) -> None:
        """estimate_messages returns the sum of per-message estimates."""
        estimator = HeuristicEstimator()
        msgs = [_msg("system", "you are helpful"), _msg("user", "hi")]
        expected = sum(_char_len(m) for m in msgs)
        assert estimator.estimate_messages(msgs) == expected

    def test_estimate_empty_list(self) -> None:
        """estimate_messages of an empty list returns 0."""
        estimator = HeuristicEstimator()
        assert estimator.estimate_messages([]) == 0

    def test_estimate_single_message(self) -> None:
        """estimate_messages with one message matches estimate_message."""
        estimator = HeuristicEstimator()
        msg = _msg("assistant", "done")
        assert estimator.estimate_messages([msg]) == (
            estimator.estimate_message(msg)
        )
    def test_unicode_content_counted_as_single_chars(self) -> None:
        """Unicode characters are counted as individual code points."""
        estimator = HeuristicEstimator()
        msg = {"role": "user", "content": "こんにちは"}
        result = estimator.estimate_message(msg)
        assert result == _char_len(msg)

    def test_satisfies_token_estimator_protocol(self) -> None:
        """HeuristicEstimator is an instance of the TokenEstimator protocol."""
        estimator = HeuristicEstimator()
        assert isinstance(estimator, TokenEstimator)

    def test_deterministic(self) -> None:
        """Same message always produces the same token count."""
        estimator = HeuristicEstimator()
        msg = _msg("user", "test")
        first_count = estimator.estimate_message(msg)
        assert first_count == estimator.estimate_message(msg)

# ---------------------------------------------------------------------------
# TruncateCompactor unit tests
# ---------------------------------------------------------------------------

class TestTruncateCompactorDisabled:
    """Compactor with enabled=False must be a no-op."""

    def test_disabled_returns_original_messages(self) -> None:
        """Disabled compactor returns original message list unchanged."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("user", "x" * 200)]
        config = CompactionConfigSchema(enabled=False, max_tokens=1)
        result = compactor.compact(msgs, config)
        assert result.compacted is False
        assert result.messages == msgs

    def test_disabled_result_fields(self) -> None:
        """Disabled result has matching original and compacted counts."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("user", "hello"), _msg("assistant", "world")]
        config = CompactionConfigSchema(enabled=False, max_tokens=1)
        result = compactor.compact(msgs, config)
        assert result.original_count == 2
        assert result.compacted_count == 2
        assert result.tokens_before == result.tokens_after


class TestTruncateCompactorBelowThreshold:
    """Compactor must not compact when tokens <= max_tokens."""

    def test_below_threshold_no_compaction(self) -> None:
        """Messages well below max_tokens are left unchanged."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("user", "hi")]
        config = CompactionConfigSchema(
            max_tokens=100_000,
            target_tokens=80_000,
        )
        result = compactor.compact(msgs, config)
        assert result.compacted is False
        assert result.messages == msgs

    def test_at_exact_threshold_no_compaction(self) -> None:
        """Messages exactly at max_tokens are not compacted."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("user", "x")]
        tokens = estimator.estimate_messages(msgs)
        config = CompactionConfigSchema(
            max_tokens=tokens,
            target_tokens=tokens - 1,
        )
        result = compactor.compact(msgs, config)
        assert result.compacted is False


class TestTruncateCompactorAboveThreshold:
    """Compactor must prune messages when tokens exceed max_tokens."""

    def _make_messages(
        self,
        count: int,
        content_len: int = 40,
    ) -> list[dict[str, Any]]:
        return [_msg("user", "a" * content_len) for _ in range(count)]
    def test_compaction_reduces_token_count(self) -> None:
        """After compaction tokens_after <= target_tokens."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = self._make_messages(20, content_len=60)
        config = CompactionConfigSchema(
            max_tokens=100,
            target_tokens=50,
            keep_recent_rounds=0,
        )
        result = compactor.compact(msgs, config)
        assert result.compacted is True
        assert result.tokens_after <= config.target_tokens

    def test_compaction_result_flagged(self) -> None:
        """Compacted field is True when pruning occurred."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = self._make_messages(10, content_len=50)
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=20,
            keep_recent_rounds=0,
        )
        result = compactor.compact(msgs, config)
        assert result.compacted is True

    def test_compacted_count_less_than_original(self) -> None:
        """compacted_count < original_count after pruning."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = self._make_messages(10, content_len=50)
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=20,
            keep_recent_rounds=0,
        )
        result = compactor.compact(msgs, config)
        assert result.compacted_count < result.original_count

    def test_strategy_always_truncate(self) -> None:
        """strategy_used is always TRUNCATE for TruncateCompactor."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = self._make_messages(10, content_len=50)
        config = CompactionConfigSchema(max_tokens=1, target_tokens=0)
        result = compactor.compact(msgs, config)
        assert result.strategy_used == CompactionStrategy.TRUNCATE


class TestTruncateCompactorSystemMessage:
    """System message at index 0 MUST NOT be pruned."""

    def test_system_message_preserved(self) -> None:
        """System message at index 0 survives compaction."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        system = _msg("system", "you are an assistant")
        user_msgs = [_msg("user", "x" * 60) for _ in range(10)]
        msgs = [system, *user_msgs]
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=10,
            keep_recent_rounds=0,
        )
        result = compactor.compact(msgs, config)
        assert result.messages[0]["role"] == "system"
        assert result.messages[0]["content"] == "you are an assistant"

    def test_only_system_message_returns_as_is(self) -> None:
        """A single system message is not removed even at zero tokens."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("system", "prompt")]
        config = CompactionConfigSchema(max_tokens=1, target_tokens=0)
        result = compactor.compact(msgs, config)
        assert len(result.messages) == 1
        assert result.messages[0]["role"] == "system"


class TestTruncateCompactorKeepRecentRounds:
    """keep_recent_rounds limits how many messages can be removed."""

    def test_keep_recent_rounds_respected(self) -> None:
        """Compactor stops pruning when len(messages) == keep_recent_rounds."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("user", "a" * 50) for _ in range(10)]
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=10,
            keep_recent_rounds=5,
        )
        result = compactor.compact(msgs, config)
        assert len(result.messages) >= 5

    def test_keep_recent_rounds_zero_allows_full_prune(self) -> None:
        """keep_recent_rounds=0 allows all messages to be removed."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        msgs = [_msg("user", "a" * 50) for _ in range(10)]
        config = CompactionConfigSchema(
            max_tokens=1,
            target_tokens=0,
            keep_recent_rounds=0,
        )
        result = compactor.compact(msgs, config)
        assert len(result.messages) == 0


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    """TruncateCompactor satisfies ContextCompactor protocol."""

    def test_truncate_compactor_satisfies_protocol(self) -> None:
        """TruncateCompactor is a valid ContextCompactor."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        assert isinstance(compactor, ContextCompactor)

    def test_compaction_result_is_model(self) -> None:
        """compact() always returns a CompactionResult instance."""
        estimator = HeuristicEstimator()
        compactor = TruncateCompactor(estimator)
        config = CompactionConfigSchema()
        result = compactor.compact([], config)
        assert isinstance(result, CompactionResult)


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

class TestFactories:
    """get_default_estimator and get_default_compactor return valid objects."""

    def test_get_default_estimator_returns_token_estimator(self) -> None:
        """Default estimator satisfies the TokenEstimator protocol."""
        estimator = get_default_estimator()
        assert isinstance(estimator, TokenEstimator)

    def test_get_default_compactor_returns_context_compactor(self) -> None:
        """Default compactor satisfies the ContextCompactor protocol."""
        compactor = get_default_compactor()
        assert isinstance(compactor, ContextCompactor)

    def test_default_estimator_is_heuristic(self) -> None:
        """Default estimator is a HeuristicEstimator instance."""
        estimator = get_default_estimator()
        assert isinstance(estimator, HeuristicEstimator)

    def test_default_compactor_is_truncate(self) -> None:
        """Default compactor is a TruncateCompactor instance."""
        compactor = get_default_compactor()
        assert isinstance(compactor, TruncateCompactor)


# ---------------------------------------------------------------------------
# loop.run() integration tests
# ---------------------------------------------------------------------------

def _make_trace() -> MagicMock:
    """Return a MagicMock that satisfies the Trace interface."""
    trace = MagicMock()
    trace.log = MagicMock()
    return trace


def _make_registry() -> MagicMock:
    """Return a minimal mock ToolRegistry."""
    registry = MagicMock()
    registry.get_serialized_tools.return_value = []
    return registry


def _provider_response(content: str) -> dict[str, Any]:
    """Construct a minimal successful provider response dict."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": None,
                }
            }
        ]
    }


class TestLoopCompactionIntegration:
    """loop.run() compaction integration tests with a stubbed provider."""

    @patch("pelmeni.loop.provider.chat")
    def test_loop_runs_without_compaction_when_below_threshold(
        self,
        mock_chat: MagicMock,
    ) -> None:
        """loop.run() calls provider once when tokens are below max_tokens."""
        mock_chat.return_value = _provider_response("hello")
        msgs: list[dict[str, Any]] = [_msg("user", "hi")]
        config = CompactionConfigSchema(max_tokens=100_000)
        trace = _make_trace()
        registry = _make_registry()


        result = run(
            msgs,
            trace,
            registry=registry,
            compaction_config=config,
        )
        assert result == "hello"
        mock_chat.assert_called_once()
        # No compaction log should have fired.
        logged_events = [call.args[0] for call in trace.log.call_args_list]
        assert "context_compacted" not in logged_events

    @patch("pelmeni.loop.provider.chat")
    def test_loop_compacts_and_logs_context_compacted(
        self,
        mock_chat: MagicMock,
    ) -> None:
        """loop.run() logs event when messages exceed max_tokens."""
        mock_chat.return_value = _provider_response("done")
        # Build a large message history that exceeds the tiny max_tokens.
        large_msgs: list[dict[str, Any]] = [
            _msg("user", "word " * 100) for _ in range(20)
        ]
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=20,
            keep_recent_rounds=0,
        )
        trace = _make_trace()
        registry = _make_registry()

        result = run(
            large_msgs,
            trace,
            registry=registry,
            compaction_config=config,
        )
        assert result == "done"
        logged_events = [call.args[0] for call in trace.log.call_args_list]
        assert "context_compacted" in logged_events

    @patch("pelmeni.loop.provider.chat")
    def test_loop_mutates_messages_in_place_on_compaction(
        self,
        mock_chat: MagicMock,
    ) -> None:
        """loop.run() mutates message list in-place on compaction."""
        mock_chat.return_value = _provider_response("ok")
        original_msgs: list[dict[str, Any]] = [
            _msg("user", "a" * 100) for _ in range(20)
        ]
        initial_id = id(original_msgs)
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=20,
            keep_recent_rounds=0,
        )
        trace = _make_trace()
        registry = _make_registry()

        run(original_msgs, trace, registry=registry, compaction_config=config)
        # Same list object — mutated in-place via messages[:] = …
        assert id(original_msgs) == initial_id

    @patch("pelmeni.loop.provider.chat")
    def test_loop_preserves_system_message_across_compaction(
        self,
        mock_chat: MagicMock,
    ) -> None:
        """System message at index 0 remains after compaction in the loop."""
        mock_chat.return_value = _provider_response("fine")
        system_content = "you are a helpful assistant"
        msgs: list[dict[str, Any]] = [
            _msg("system", system_content),
            *[_msg("user", "b" * 60) for _ in range(15)],
        ]
        config = CompactionConfigSchema(
            max_tokens=50,
            target_tokens=20,
            keep_recent_rounds=0,
        )
        trace = _make_trace()
        registry = _make_registry()


        run(msgs, trace, registry=registry, compaction_config=config)
        assert msgs[0]["content"] == system_content

    @patch("pelmeni.loop.provider.chat")
    def test_loop_returns_empty_string_on_provider_error(
        self,
        mock_chat: MagicMock,
    ) -> None:
        """loop.run() returns '' when the provider raises ProviderError."""
        mock_chat.side_effect = ProviderError("api down")
        msgs = [_msg("user", "hello")]
        registry = _make_registry()
        trace = _make_trace()
        result = run(msgs, trace, registry=registry)
        assert result == ""

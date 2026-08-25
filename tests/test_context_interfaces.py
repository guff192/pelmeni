"""Contract tests for context protocol interfaces.

These tests verify that runtime-checkable TokenEstimator and
ContextCompactor protocols behave as expected with isinstance.
"""

from pelmeni.context.protocol import ContextCompactor, TokenEstimator
from pelmeni.domain.messages import Message, UserMessage
from pelmeni.dto.context import CompactionConfigSchema, CompactionResult


class _GoodEstimator:
    """Simple conforming implementation of ``TokenEstimator``."""

    def estimate_message(self, message: Message) -> int:
        return len(str(message))

    def estimate_messages(self, messages: list[Message]) -> int:
        return sum(self.estimate_message(msg) for msg in messages)


class _BadEstimator:
    """Missing estimate_messages method - should not satisfy protocol."""

    def estimate_message(  # pragma: no cover
        self,
        message: Message,
    ) -> int:
        return len(str(message))


class _GoodCompactor:
    """Conforming ContextCompactor implementation."""

    def compact(
        self,
        messages: list[Message],
        config: CompactionConfigSchema,
    ) -> CompactionResult:
        return CompactionResult(
            compacted=False,
            original_count=len(messages),
            compacted_count=len(messages),
            tokens_before=0,
            tokens_after=0,
            messages=messages,
            strategy_used=config.strategy,
        )


class _BadCompactor:
    """Does not implement compact - protocol check should fail."""

    def unrelated(self) -> None:  # pragma: no cover
        pass


def test_token_estimator_conforms() -> None:
    """A class implementing both methods passes ``isinstance`` check."""
    assert isinstance(_GoodEstimator(), TokenEstimator)


def test_token_estimator_missing_method_fails() -> None:
    """Missing ``estimate_messages`` should cause protocol check to fail."""
    assert not isinstance(_BadEstimator(), TokenEstimator)


def test_context_compactor_conforms() -> None:
    """Class with compact method satisfies ContextCompactor protocol."""
    assert isinstance(_GoodCompactor(), ContextCompactor)


def test_context_compactor_missing_method_fails() -> None:
    """Without ``compact`` the protocol check must fail."""
    assert not isinstance(_BadCompactor(), ContextCompactor)


def test_protocol_types_distinct() -> None:
    """TokenEstimator and ContextCompactor are distinct protocol types."""
    assert TokenEstimator is not ContextCompactor


def test_good_estimator_works_with_domain_messages() -> None:
    """GoodEstimator operates on domain Message objects."""
    estimator = _GoodEstimator()
    msg = UserMessage(content="hello")
    assert estimator.estimate_message(msg) > 0
    assert estimator.estimate_messages([msg]) > 0

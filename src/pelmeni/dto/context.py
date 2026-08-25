"""Data transfer objects for Pelmeni context handling."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pelmeni.domain.messages import Message  # noqa: TC001


class CompactionStrategy(StrEnum):
    """Enum of available compaction strategies."""

    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"


class CompactionResult(BaseModel):
    """Result of a compaction operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    compacted: bool
    original_count: int
    compacted_count: int
    tokens_before: int
    tokens_after: int
    messages: list[Message] = Field(default_factory=list)
    strategy_used: CompactionStrategy


class CompactionConfigSchema(BaseModel):
    """Configuration schema for message compaction."""

    enabled: bool = True
    max_tokens: int = 8000
    target_tokens: int = 4000
    keep_recent_rounds: int = 3
    strategy: CompactionStrategy = CompactionStrategy.TRUNCATE

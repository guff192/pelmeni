"""Data transfer objects for Pelmeni context handling."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CompactionStrategy(StrEnum):
    """Enum of available compaction strategies."""

    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"


class CompactionResult(BaseModel):
    """Result of a compaction operation."""

    compacted: bool
    original_count: int
    compacted_count: int
    tokens_before: int
    tokens_after: int
    messages: list[dict[str, Any]] = Field(default_factory=list)
    strategy_used: CompactionStrategy


class CompactionConfigSchema(BaseModel):
    """Configuration schema for message compaction."""

    enabled: bool = True
    max_tokens: int = 8000
    target_tokens: int = 4000
    keep_recent_rounds: int = 3
    strategy: CompactionStrategy = CompactionStrategy.TRUNCATE

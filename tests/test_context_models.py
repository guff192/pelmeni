"""Tests for compaction DTOs and config models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pelmeni.config.models import AgentModelSchema, AppConfigSchema
from pelmeni.domain.messages import UserMessage
from pelmeni.dto.context import (
    CompactionConfigSchema,
    CompactionResult,
    CompactionStrategy,
)


def test_compaction_strategy_values() -> None:
    """CompactionStrategy enum exposes expected string values."""
    assert {s.value for s in CompactionStrategy} == {"truncate", "summarize"}
    assert CompactionStrategy.TRUNCATE == "truncate"
    assert CompactionStrategy.SUMMARIZE == "summarize"


def test_compaction_result_fields() -> None:
    """CompactionResult DTO contains all required fields and validates types."""
    msg = UserMessage(content="info")
    result = CompactionResult(
        compacted=True,
        original_count=5,
        compacted_count=1,
        tokens_before=100,
        tokens_after=20,
        messages=[msg],
        strategy_used=CompactionStrategy.TRUNCATE,
    )
    assert result.compacted is True
    assert result.original_count == 5
    assert result.compacted_count == 1
    assert result.tokens_before == 100
    assert result.tokens_after == 20
    assert result.messages == [msg]
    assert result.strategy_used == CompactionStrategy.TRUNCATE


def test_compaction_config_schema_defaults() -> None:
    """CompactionConfigSchema validates defaults when fields omitted."""
    cfg = CompactionConfigSchema()
    assert cfg.enabled is True
    assert cfg.max_tokens == 8000
    assert cfg.target_tokens == 4000
    assert cfg.keep_recent_rounds == 3
    assert cfg.strategy == CompactionStrategy.TRUNCATE
    assert cfg.max_tool_chars == 2000


def test_agent_model_schema_accepts_optional_compaction() -> None:
    """AgentModelSchema can include an optional compaction configuration."""
    schema = AgentModelSchema(
        model="fast",
        compaction=CompactionConfigSchema(enabled=False),
    )
    assert schema.model == "fast"
    assert isinstance(schema.compaction, CompactionConfigSchema)
    assert schema.compaction.enabled is False


def test_app_config_schema_includes_compaction_default() -> None:
    """AppConfigSchema includes a compaction field with default values."""
    app_cfg = AppConfigSchema(
        models={"local": "openai:gpt-4o"},
        agents={"default": AgentModelSchema(model="local")},
    )
    assert isinstance(app_cfg.compaction, CompactionConfigSchema)
    default = CompactionConfigSchema()
    assert app_cfg.compaction == default


def test_compaction_config_schema_max_tool_chars_validation() -> None:
    """Validate max_tool_chars accepts >=100 and rejects <100."""
    assert CompactionConfigSchema(max_tool_chars=500).max_tool_chars == 500
    with pytest.raises(ValidationError):
        CompactionConfigSchema(max_tool_chars=99)

"""Validation models for application configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from pelmeni.dto.context import CompactionConfigSchema


class AgentModelSchema(BaseModel):
    """Reference from an agent role to a configured model alias."""

    model: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    compaction: CompactionConfigSchema | None = None


class HookConfigSchema(BaseModel):
    """Configuration for a single hook in the chain."""

    module: str | None = None
    tools: list[str] = Field(default_factory=list)
    fail_open: bool = False


class HooksSchema(BaseModel):
    """Top-level [hooks] config section."""

    chain: list[str] = Field(default_factory=list)


class RedisSchema(BaseModel):
    """Redis bus connection configuration."""

    url: str = "redis://localhost:6379/0"


class AppConfigSchema(BaseModel):
    """Validated shape of the TOML configuration document."""

    models: dict[str, str] = Field(min_length=1)
    agents: dict[str, AgentModelSchema] = Field(min_length=1)
    hooks: HooksSchema | None = None
    redis: RedisSchema = Field(default_factory=RedisSchema)
    compaction: CompactionConfigSchema = Field(
        default_factory=CompactionConfigSchema,
    )


class ModelSpec(BaseModel):
    """Parsed provider model specification."""

    alias: str
    provider: str
    model: str
    base_url: str | None = None

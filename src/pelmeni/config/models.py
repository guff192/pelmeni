"""Validation models for application configuration."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentModelSchema(BaseModel):
    """Reference from an agent role to a configured model alias."""

    model: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)


class HookConfigSchema(BaseModel):
    """Configuration for a single hook in the chain."""

    module: str | None = None
    tools: list[str] = Field(default_factory=list)
    fail_open: bool = False


class HooksSchema(BaseModel):
    """Top-level [hooks] config section."""

    chain: list[str] = Field(default_factory=list)


class AppConfigSchema(BaseModel):
    """Validated shape of the TOML configuration document."""

    models: dict[str, str] = Field(min_length=1)
    agents: dict[str, AgentModelSchema] = Field(min_length=1)
    hooks: HooksSchema | None = None


class ModelSpec(BaseModel):
    """Parsed provider model specification."""

    alias: str
    provider: str
    model: str
    base_url: str | None = None

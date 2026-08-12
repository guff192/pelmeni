"""Validation models for application configuration."""

from pydantic import BaseModel, Field


class AgentModelSchema(BaseModel):
    """Reference from an agent role to a configured model alias."""

    model: str = Field(min_length=1)


class AppConfigSchema(BaseModel):
    """Validated shape of the TOML configuration document."""

    models: dict[str, str] = Field(min_length=1)
    agents: dict[str, AgentModelSchema] = Field(min_length=1)


class ModelSpec(BaseModel):
    """Parsed provider model specification."""

    alias: str
    provider: str
    model: str
    base_url: str | None = None

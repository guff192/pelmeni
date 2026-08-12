"""Configuration validation collaborator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from pathlib import Path

    from pelmeni._config_parser import ConfigParser

from pelmeni._config_types import AgentConfig, ConfigError


class AgentModelSchema(BaseModel):
    """Pydantic schema for agent model reference."""

    model: str = Field(min_length=1)


class AppConfigSchema(BaseModel):
    """Pydantic schema for raw app configuration."""

    models: dict[str, str] = Field(min_length=1)
    agents: dict[str, AgentModelSchema] = Field(min_length=1)


class ConfigValidator:
    """Collaborator responsible for validating schemas and configs."""

    def __init__(self, path: Path, parser: ConfigParser) -> None:
        self._path = path
        self._parser = parser

    def verify_schema(self, raw_config: dict[str, object]) -> AppConfigSchema:
        """Validate raw TOML dict against Pydantic schema."""
        try:
            return AppConfigSchema.model_validate(raw_config)
        except ValidationError as exc:
            msg = f"Invalid configuration schema in '{self._path}': {exc}"
            raise ConfigError(msg) from exc

    def verify_models(self, raw_models: dict[str, str]) -> dict[str, str]:
        """Validate all model specifications."""
        models: dict[str, str] = {}
        for alias, spec in raw_models.items():
            self._parser.parse_model_spec(alias, spec)
            models[alias] = spec
        return models

    def verify_agents(
        self,
        raw_agents: dict[str, AgentModelSchema],
        models: dict[str, str],
    ) -> dict[str, AgentConfig]:
        """Validate agent definitions and references."""
        agents: dict[str, AgentConfig] = {}
        for agent_name, agent_data in raw_agents.items():
            if agent_data.model in models:
                agents[agent_name] = AgentConfig(model=agent_data.model)
            else:
                available = list(models.keys())
                msg = (
                    f"Agent '{agent_name}' references undefined model alias "
                    f"'{agent_data.model}'. Available aliases: {available}"
                )
                raise ConfigError(msg)
        return agents

"""Application configuration facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from pelmeni.config.models import (
    AgentModelSchema,
    AppConfigSchema,
    CompactionConfigSchema,
    HooksSchema,
    ModelSpec,
    RedisSchema,
)
from pelmeni.config.parser import ConfigError, load_toml, parse_model_spec

CONFIG_PATH = Path("config.toml")
DEFAULT_AGENT = "default"


def _validate_models(models: dict[str, str]) -> dict[str, str]:
    for alias, specification in models.items():
        parse_model_spec(alias, specification)
    return models


def _extract_raw_hooks(raw_config: dict[str, object]) -> dict[str, dict]:
    hooks_table = raw_config.get("hooks", {})
    if not isinstance(hooks_table, dict):
        return {}
    raw_hooks = {}
    for name, hook_data in hooks_table.items():
        if name != "chain" or not isinstance(hook_data, dict):
            continue
        raw_hooks[name] = hook_data
    return raw_hooks


def _resolve_target_path(path: Path) -> Path:
    if not path.exists() and path == CONFIG_PATH:
        user_path = Path.home() / ".config" / "pelmeni" / "config.toml"
        if user_path.exists():
            return user_path
    return path


def _validate_schema(
    raw_config: dict[str, object],
    target_path: Path,
) -> AppConfigSchema:
    try:
        return AppConfigSchema.model_validate(raw_config)
    except ValidationError as exc:
        message = f"Invalid configuration schema in '{target_path}': {exc}"
        raise ConfigError(message) from exc


def _validate_agents(
    agents: dict[str, AgentModelSchema],
    models: dict[str, str],
) -> dict[str, AgentModelSchema]:
    for agent_name, agent_config in agents.items():
        if agent_config.model not in models:
            available = list(models)
            message = (
                f"Agent '{agent_name}' references undefined model alias "
                f"'{agent_config.model}'. Available aliases: {available}"
            )
            raise ConfigError(message)
    return agents


@dataclass(frozen=True)
class AppConfig:
    """Validated models and agent mappings."""

    models: dict[str, str]
    agents: dict[str, AgentModelSchema]
    hooks: HooksSchema | None = None
    raw_hooks: dict[str, dict] = field(default_factory=dict)
    redis: RedisSchema = field(default_factory=RedisSchema)
    compaction: CompactionConfigSchema = field(
        default_factory=CompactionConfigSchema,
    )


class ConfigService:
    """Load, validate, and resolve application configuration."""

    def __init__(self, path: Path | str = CONFIG_PATH) -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        """Load and validate application configuration from disk."""
        target_path = _resolve_target_path(self.path)
        if not target_path.exists():
            message = f"Config file not found: {self.path}"
            raise ConfigError(message)
        raw_config = load_toml(target_path)
        validated = _validate_schema(raw_config, target_path)
        if DEFAULT_AGENT not in validated.agents:
            message = f"Missing required agent: default in '{target_path}'"
            raise ConfigError(message)

        models = _validate_models(validated.models)
        return AppConfig(
            models=models,
            agents=_validate_agents(validated.agents, models),
            hooks=validated.hooks,
            raw_hooks=_extract_raw_hooks(raw_config),
            redis=validated.redis,
            compaction=validated.compaction,
        )

    def resolve(
        self,
        agent: str = DEFAULT_AGENT,
        config: AppConfig | None = None,
    ) -> ModelSpec:
        """Resolve an agent role to its provider model specification."""
        target_config = self.load() if config is None else config
        agent_config = target_config.agents.get(agent)
        if agent_config is None:
            agent_config = target_config.agents.get(DEFAULT_AGENT)
        if agent_config is None:
            message = (
                f"No configuration found for agent '{agent}' and no "
                "'default' agent configured"
            )
            raise ConfigError(message)

        alias = agent_config.model
        specification = target_config.models.get(alias)
        if specification is None:
            message = (
                f"Unknown model alias '{alias}' requested by agent '{agent}'"
            )
            raise ConfigError(message)
        return parse_model_spec(alias, specification)

    def resolve_compaction_config(
        self,
        agent: str = DEFAULT_AGENT,
        config: AppConfig | None = None,
    ) -> CompactionConfigSchema:
        """Resolve compaction configuration for a specific agent role."""
        target_config = self.load() if config is None else config
        agent_config = target_config.agents.get(agent)
        if agent_config is not None and agent_config.compaction is not None:
            return agent_config.compaction
        return target_config.compaction

    def parse_model_spec(self, alias: str, specification: str) -> ModelSpec:
        """Parse a provider:model[@url] specification string."""
        return parse_model_spec(alias, specification)

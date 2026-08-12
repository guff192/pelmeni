"""Configuration loader and model resolver for pelmeni."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pelmeni._config_helpers import ConfigValidator
from pelmeni._config_parser import ConfigParser
from pelmeni._config_types import AgentConfig, ConfigError, ResolvedModel

CONFIG_PATH = Path("config.toml")


@dataclass(frozen=True)
class AppConfig:
    """Application configuration containing models and agents mapping."""

    models: dict[str, str]
    agents: dict[str, AgentConfig]


class ConfigService:
    """Service for loading, parsing, and resolving configuration."""

    def __init__(self, path: Path | str = CONFIG_PATH) -> None:
        self.path = Path(path)
        self._parser = ConfigParser(self.path)
        self._validator = ConfigValidator(self.path, self._parser)

    def load(self) -> AppConfig:
        """Load and validate AppConfig from file."""
        target_path = self._resolve_target_path()
        if not target_path.exists():
            msg = f"Config file not found: {self.path}"
            raise ConfigError(msg)

        raw_data = self._parser.read_toml()
        validated = self._validator.verify_schema(raw_data)

        if "default" not in validated.agents:
            msg = f"Missing required agent: default in '{target_path}'"
            raise ConfigError(msg)

        return AppConfig(
            models=self._validator.verify_models(validated.models),
            agents=self._validator.verify_agents(
                validated.agents,
                self._validator.verify_models(validated.models),
            ),
        )

    def resolve(
        self, agent: str = "default", config: AppConfig | None = None
    ) -> ResolvedModel:
        """Resolve agent role to a ResolvedModel instance."""
        target_config = self.load() if config is None else config
        agent_cfg = target_config.agents.get(agent)
        if agent_cfg is None:
            agent_cfg = target_config.agents.get("default")

        if agent_cfg is None:
            msg = (
                f"No configuration found for agent '{agent}' and no "
                "'default' agent configured"
            )
            raise ConfigError(msg)

        alias = agent_cfg.model
        spec = target_config.models.get(alias)
        if spec is None:
            msg = f"Unknown model alias '{alias}' requested by agent '{agent}'"
            raise ConfigError(msg)

        return self.parse_model_spec(alias, spec)

    def parse_model_spec(self, alias: str, spec: str) -> ResolvedModel:
        """Parse a provider:model[@url] specification string."""
        return self._parser.parse_model_spec(alias, spec)

    def _resolve_target_path(self) -> Path:
        """Resolve path to local or user config file."""
        if not self.path.exists() and self.path == CONFIG_PATH:
            user_config = Path.home() / ".config" / "pelmeni" / "config.toml"
            if user_config.exists():
                self._parser = ConfigParser(user_config)
                self._validator = ConfigValidator(user_config, self._parser)
                return user_config
        return self.path

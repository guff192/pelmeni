"""Tests for pelmeni configuration loading, parsing, and model resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from pelmeni.config import AppConfig, ConfigService
from pelmeni.config.models import (
    AgentModelSchema,
    AppConfigSchema,
    HooksSchema,
)
from pelmeni.config.parser import ConfigError


def test_parse_model_spec_standard() -> None:
    """Test parsing standard provider:model specification."""
    resolved = ConfigService().parse_model_spec("default", "openai:gpt-4o")
    assert resolved.alias == "default"
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-4o"
    assert resolved.base_url is None


def test_parse_model_spec_openai_compatible_with_url() -> None:
    """Test parsing openai-compatible specification with base URL."""
    resolved = ConfigService().parse_model_spec(
        "local", "openai-compatible:qwen3-8b@http://localhost:1234/v1"
    )
    assert resolved.alias == "local"
    assert resolved.provider == "openai-compatible"
    assert resolved.model == "qwen3-8b"
    assert resolved.base_url == "http://localhost:1234/v1"


def test_parse_model_spec_openai_compatible_missing_url() -> None:
    """Test parsing openai-compatible spec without URL raises error."""
    with pytest.raises(ConfigError, match="requires @url"):
        ConfigService().parse_model_spec("local", "openai-compatible:qwen3-8b")


def test_parse_model_spec_url_not_allowed() -> None:
    """Test parsing non-compatible spec with URL raises error."""
    with pytest.raises(ConfigError, match="URL override not allowed"):
        ConfigService().parse_model_spec(
            "bad", "openai:gpt-4o@http://localhost:1234/v1"
        )


def test_parse_model_spec_invalid_format() -> None:
    """Test parsing invalid model specification format raises error."""
    with pytest.raises(ConfigError, match="Invalid model specification"):
        ConfigService().parse_model_spec("bad", "invalid-format")


def test_load_config_valid(tmp_path: Path) -> None:
    """Test loading valid configuration file using ConfigService."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[models]\n"
        'default = "openai:gpt-4o"\n'
        'fast = "anthropic:claude-3-haiku"\n\n'
        "[agents]\n"
        'default = { model = "default" }\n'
        'worker = { model = "fast" }\n',
        encoding="utf-8",
    )
    service = ConfigService(path=config_file)
    cfg = service.load()
    assert isinstance(cfg, AppConfig)
    assert cfg.models["default"] == "openai:gpt-4o"
    assert cfg.agents["default"] == AgentModelSchema(model="default")
    assert cfg.agents["worker"] == AgentModelSchema(model="fast")


def test_load_config_file_not_found(tmp_path: Path) -> None:
    """Test loading non-existent configuration file raises error."""
    missing_file = tmp_path / "nonexistent.toml"
    service = ConfigService(path=missing_file)
    with pytest.raises(ConfigError, match="Config file not found"):
        service.load()


def test_load_config_missing_default_agent(tmp_path: Path) -> None:
    """Test loading config missing 'default' agent raises error."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[models]\n"
        'default = "openai:gpt-4o"\n\n'
        "[agents]\n"
        'worker = { model = "default" }\n',
        encoding="utf-8",
    )
    service = ConfigService(path=config_file)
    with pytest.raises(ConfigError, match="Missing required agent: default"):
        service.load()


def test_load_config_unresolved_model_alias(tmp_path: Path) -> None:
    """Test loading config with unresolved model alias raises error."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[models]\n"
        'default = "openai:gpt-4o"\n\n'
        "[agents]\n"
        'default = { model = "default" }\n'
        'worker = { model = "unknown-model" }\n',
        encoding="utf-8",
    )
    service = ConfigService(path=config_file)
    with pytest.raises(ConfigError, match="references undefined model alias"):
        service.load()


def test_load_config_malformed_toml(tmp_path: Path) -> None:
    """Test loading malformed TOML raises ConfigError."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("[models\ndefault = invalid_toml", encoding="utf-8")
    service = ConfigService(path=config_file)
    with pytest.raises(ConfigError):
        service.load()


def test_resolve_model_exact_role() -> None:
    """Test resolving model for specific agent role using ConfigService."""
    cfg = AppConfig(
        models={
            "m1": "openai:gpt-4o",
            "m2": "anthropic:claude-3-5-sonnet",
        },
        agents={
            "default": AgentModelSchema(model="m1"),
            "worker": AgentModelSchema(model="m2"),
        },
    )
    service = ConfigService()
    resolved = service.resolve("worker", config=cfg)
    assert resolved.alias == "m2"
    assert resolved.provider == "anthropic"
    assert resolved.model == "claude-3-5-sonnet"


def test_resolve_model_fallback_to_default() -> None:
    """Test falling back to default agent role when unknown requested."""
    cfg = AppConfig(
        models={
            "m1": "openai:gpt-4o",
        },
        agents={
            "default": AgentModelSchema(model="m1"),
        },
    )
    service = ConfigService()
    resolved = service.resolve("specialist", config=cfg)
    assert resolved.alias == "m1"
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-4o"


def test_hooks_config_parsed() -> None:
    """AppConfigSchema accepts a hooks section."""
    schema = AppConfigSchema(
        models={"local": "openai:gpt-4o"},
        agents={"default": AgentModelSchema(model="local")},
        hooks=HooksSchema(chain=["blocklist"]),
    )

    assert schema.hooks is not None
    assert schema.hooks.chain == ["blocklist"]


def test_hooks_config_optional() -> None:
    """Missing hooks config defaults to None."""
    schema = AppConfigSchema(
        models={"local": "openai:gpt-4o"},
        agents={"default": AgentModelSchema(model="local")},
    )

    assert schema.hooks is None

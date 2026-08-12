"""TOML loading and model specification parsing."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Never

from pelmeni.config.models import ModelSpec

if TYPE_CHECKING:
    from pathlib import Path


class ConfigError(Exception):
    """Configuration loading or validation error."""


def _raise_config_error(message: str, cause: Exception | None = None) -> Never:
    if cause is not None:
        raise ConfigError(message) from cause
    raise ConfigError(message)


def load_toml(path: Path) -> dict[str, object]:
    """Load and decode a TOML configuration document."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Failed to parse TOML config '{path}': {exc}"
        _raise_config_error(message, exc)
    try:
        return tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        message = f"Failed to parse TOML config '{path}': {exc}"
        _raise_config_error(message, exc)


def parse_model_spec(alias: str, specification: str) -> ModelSpec:
    """Parse a provider:model[@url] specification string."""
    if not specification or not isinstance(specification, str):
        message = f"Model spec for alias '{alias}' must be a non-empty string"
        _raise_config_error(message)
    if ":" not in specification:
        message = (
            f"Invalid model specification '{specification}' for alias "
            f"'{alias}': must be in format 'provider:model' or "
            "'provider:model@url'"
        )
        _raise_config_error(message)

    provider, model, parsed_url = _split_model_spec(specification)
    if not model:
        message = (
            f"Empty model name in model spec '{specification}' for alias "
            f"'{alias}'"
        )
        _raise_config_error(message)
    _validate_provider_url(alias, specification, provider, parsed_url)
    return ModelSpec(
        alias=alias,
        provider=provider,
        model=model,
        base_url=parsed_url,
    )


def _split_model_spec(specification: str) -> tuple[str, str, str | None]:
    provider, model_and_url = specification.split(":", 1)
    model, separator, base_url = model_and_url.partition("@")
    return (
        provider.strip(),
        model.strip(),
        base_url.strip() if separator else None,
    )


def _validate_provider_url(
    alias: str,
    specification: str,
    provider: str,
    base_url: str | None,
) -> None:
    if provider == "openai-compatible" and not base_url:
        message = (
            f"Provider 'openai-compatible' in spec '{specification}' for "
            f"alias '{alias}' requires @url "
            "(format: openai-compatible:model@url)"
        )
        _raise_config_error(message)
    if provider != "openai-compatible" and base_url:
        message = (
            f"URL override not allowed for provider '{provider}' in spec "
            f"'{specification}' for alias '{alias}'"
        )
        _raise_config_error(message)

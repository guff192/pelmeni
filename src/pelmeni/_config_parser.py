"""Configuration parser collaborator."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Never

if TYPE_CHECKING:
    from pathlib import Path

from pelmeni._config_types import ConfigError, ResolvedModel


def _raise(msg: str, cause: Exception | None = None) -> Never:
    if cause is not None:
        raise ConfigError(msg) from cause
    raise ConfigError(msg)


class ConfigParser:
    """Collaborator responsible for reading TOML and parsing model specs."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read_toml(self) -> dict[str, object]:
        """Read and decode TOML configuration file."""
        raw_text = self._read_text()
        try:
            toml_payload = tomllib.loads(raw_text)
        except tomllib.TOMLDecodeError as exc:
            _raise(f"Failed to parse TOML config '{self._path}': {exc}", exc)
        else:
            if not isinstance(toml_payload, dict):
                _raise(f"Config root in '{self._path}' must be a TOML table")
            return toml_payload

    def parse_model_spec(self, alias: str, spec: str) -> ResolvedModel:
        """Parse a provider:model[@url] specification string."""
        if not spec or not isinstance(spec, str):
            _raise(f"Model spec for alias '{alias}' must be a non-empty string")

        if ":" not in spec:
            msg = (
                f"Invalid model specification '{spec}' for alias '{alias}': "
                "must be in format 'provider:model' or 'provider:model@url'"
            )
            _raise(msg)

        provider, rest = spec.split(":", 1)
        provider = provider.strip()
        if not provider:
            _raise(f"Empty provider in model spec '{spec}' for alias '{alias}'")

        if "@" in rest:
            model, base_url = rest.split("@", 1)
            model = model.strip()
            base_url = base_url.strip()
        else:
            model = rest.strip()
            base_url = None

        if not model:
            _raise(
                f"Empty model name in model spec '{spec}' for alias '{alias}'"
            )
        self._check_provider_url_rules(alias, spec, provider, base_url)

        return ResolvedModel(
            alias=alias,
            provider=provider,
            model=model,
            base_url=base_url,
        )

    def _read_text(self) -> str:
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError as exc:
            _raise(f"Failed to parse TOML config '{self._path}': {exc}", exc)
            raise

    def _check_provider_url_rules(
        self, alias: str, spec: str, provider: str, base_url: str | None
    ) -> None:
        if provider == "openai-compatible":
            if not base_url:
                msg = (
                    f"Provider 'openai-compatible' in spec '{spec}' for "
                    f"alias '{alias}' requires @url "
                    "(format: openai-compatible:model@url)"
                )
                _raise(msg)
        elif base_url:
            msg = (
                f"URL override not allowed for provider '{provider}' in spec "
                f"'{spec}' for alias '{alias}'"
            )
            _raise(msg)

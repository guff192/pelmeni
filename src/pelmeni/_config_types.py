"""Shared configuration types and exceptions."""

from __future__ import annotations

from dataclasses import dataclass


class ConfigError(Exception):
    """Configuration error."""


@dataclass(frozen=True)
class AgentConfig:
    """Agent configuration."""

    model: str


@dataclass(frozen=True)
class ResolvedModel:
    """Resolved provider model details."""

    alias: str
    provider: str
    model: str
    base_url: str | None = None

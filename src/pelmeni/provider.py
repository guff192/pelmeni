"""Facade provider layer dispatching to backend provider instances."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pelmeni._provider_factory import ProviderFactory
from pelmeni.auth import AuthManager
from pelmeni.config import ConfigService, ResolvedModel
from pelmeni.providers.base import Provider, ProviderError

if TYPE_CHECKING:
    from collections.abc import Sequence


class ProviderRouter:
    """Router for managing provider instance configuration and chat dispatch."""

    def __init__(
        self,
        config_service: ConfigService | None = None,
        auth_manager: AuthManager | None = None,
        factory: ProviderFactory | None = None,
    ) -> None:
        """Initialize provider router with optional services."""
        self._config_service = config_service or ConfigService()
        self._auth_manager = auth_manager or AuthManager()
        self._factory = factory or ProviderFactory()
        self._model: ResolvedModel | None = None
        self._provider: Provider | None = None

    def configure(
        self,
        agent: str = "worker",
        config_path: Path | str | None = None,
        credentials_path: Path | str | None = None,
    ) -> ResolvedModel:
        """Configure provider router for a specific agent role."""
        if config_path is not None:
            self._config_service = ConfigService(path=config_path)
        if credentials_path is not None:
            self._auth_manager = AuthManager(path=Path(credentials_path))

        resolved = self._config_service.resolve(agent)
        self._model = resolved
        self._provider = self._factory.create(
            resolved.provider,
            base_url=resolved.base_url,
        )
        return resolved

    def get_configured_model(self) -> ResolvedModel:
        """Return currently configured model or raise ProviderError."""
        if self._model is None:
            msg = "Provider layer is not configured. Call configure() first."
            raise ProviderError(msg)
        return self._model

    def describe(self) -> str:
        """Return formatted string describing current model configuration."""
        model_info = self.get_configured_model()
        parts = [
            f"alias: {model_info.alias}",
            f"provider: {model_info.provider}",
            f"model: {model_info.model}",
        ]
        if model_info.base_url:
            parts.append(f"base_url: {model_info.base_url}")
        return ", ".join(parts)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Dispatch chat request to configured provider implementation."""
        if self._model is None or self._provider is None:
            msg = "Provider layer is not configured. Call configure() first."
            raise ProviderError(msg)

        credentials = self._auth_manager.resolve(self._model.provider)

        try:
            return self._provider.chat(
                messages=messages,
                tools=tools,
                model=self._model.model,
                credentials=credentials,
            )
        except ProviderError:
            raise
        except Exception as exc:
            msg = f"Provider request failed: {exc}"
            raise ProviderError(msg) from exc


_ROUTER = ProviderRouter()


def configure(
    agent: str = "worker",
    config_path: Path | str | None = None,
    credentials_path: Path | str | None = None,
) -> ResolvedModel:
    """Configure module router for a specific agent role."""
    return _ROUTER.configure(
        agent=agent,
        config_path=config_path,
        credentials_path=credentials_path,
    )


def get_configured_model() -> ResolvedModel:
    """Return currently configured model from module router."""
    return _ROUTER.get_configured_model()


def describe() -> str:
    """Return description from module router."""
    return _ROUTER.describe()


def chat(
    messages: list[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dispatch chat via module router."""
    return _ROUTER.chat(messages=messages, tools=tools)

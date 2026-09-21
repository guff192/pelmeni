"""Credential resolution chain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from pydantic import SecretStr, TypeAdapter, ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pelmeni.auth.store import TomlCredentialStore
from pelmeni.dto.credentials import (
    ApiKeyCredentials,
    Credentials,
    NoCredentials,
)


class CredentialResolutionError(Exception):
    """Raised when credentials cannot be resolved."""


class AbstractCredentialHandler(ABC):
    """Base link in the credential resolution chain."""

    def __init__(self) -> None:
        """Initialize an unlinked handler."""
        self._next_handler: AbstractCredentialHandler | None = None

    def set_next(
        self,
        target_link: AbstractCredentialHandler,
    ) -> AbstractCredentialHandler:
        """Append and return the next link in the chain."""
        self._next_handler = target_link
        return target_link

    @abstractmethod
    def resolve_credentials(self, provider: str) -> Credentials | None:
        """Resolve credentials or delegate to the next link."""

    def _resolve_next(self, provider: str) -> Credentials | None:
        if self._next_handler is None:
            return None
        return self._next_handler.resolve_credentials(provider)


class EnvVarHandler(AbstractCredentialHandler):
    """Resolve API keys from provider-specific environment variables."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        """Initialize with an environment mapping."""
        super().__init__()
        self._environ = environ

    def resolve_credentials(self, provider: str) -> Credentials | None:
        """Return credentials from the environment when configured."""
        variable_name = self._variable_name(provider)
        raw_value = self._environ.get(variable_name)
        if raw_value is None:
            return self._resolve_next(provider)
        api_key = raw_value.strip()
        if not api_key:
            error_message = f"Environment variable {variable_name} is empty"
            raise CredentialResolutionError(error_message)
        if api_key.lower() == "none":
            return NoCredentials(provider=provider)
        return ApiKeyCredentials(
            provider=provider,
            api_key=SecretStr(api_key),
        )

    @staticmethod
    def _variable_name(provider: str) -> str:  # noqa: WPS602
        normalized = provider.replace("-", "_").upper()
        return f"PELMENI_{normalized}_API_KEY"


class TomlStoreHandler(AbstractCredentialHandler):
    """Resolve credentials from the TOML credential store."""

    _adapter: ClassVar[TypeAdapter[Credentials]] = TypeAdapter(Credentials)

    def __init__(self, store: TomlCredentialStore) -> None:
        """Initialize with a credential store."""
        super().__init__()
        self._store = store

    def resolve_credentials(self, provider: str) -> Credentials | None:
        """Return validated stored credentials when present."""
        raw_credentials = self._store.load().get(provider)
        if raw_credentials is None:
            return self._resolve_next(provider)
        payload = dict(raw_credentials)
        payload.setdefault("provider", provider)
        try:
            return self._adapter.validate_python(payload)
        except ValidationError as exc:
            error_message = f"Invalid credentials for provider '{provider}'"
            raise CredentialResolutionError(error_message) from exc


class NoAuthHandler(AbstractCredentialHandler):
    """Resolve explicit no-auth providers."""

    def __init__(self, providers: frozenset[str] | None = None) -> None:
        """Initialize with providers that permit anonymous access."""
        super().__init__()
        default_providers = frozenset(
            ("ollama", "lmstudio", "openai-compatible", "antigravity"),
        )
        self._providers = providers or default_providers

    def resolve_credentials(self, provider: str) -> Credentials | None:
        """Return a no-credentials marker for anonymous providers."""
        if provider in self._providers:
            return NoCredentials(provider=provider)
        return self._resolve_next(provider)


class CredentialResolver:
    """Facade around the credential handler chain."""

    def __init__(self, first_handler: AbstractCredentialHandler) -> None:
        """Initialize with the first chain link."""
        self._first_handler = first_handler

    def resolve_credentials(self, provider: str) -> Credentials | None:
        """Resolve credentials by walking the configured chain."""
        return self._first_handler.resolve_credentials(provider)

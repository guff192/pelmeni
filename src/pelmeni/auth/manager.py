"""Authentication manager facade."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import SecretStr, TypeAdapter, ValidationError

from pelmeni.auth.oauth.google import GoogleOAuthFlow
from pelmeni.auth.resolver import (
    CredentialResolutionError,
    CredentialResolver,
    EnvVarHandler,
    NoAuthHandler,
    TomlStoreHandler,
)
from pelmeni.auth.store import TomlCredentialStore
from pelmeni.dto.credentials import (
    ApiKeyCredentials,
    Credentials,
    NoCredentials,
)


class AuthError(Exception):
    """Raised when authentication cannot be completed."""


class AuthManager:
    """Load, save, resolve, and create provider credentials."""

    def __init__(
        self,
        path: Path | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        """Initialize authentication services."""
        credential_path = (
            path or Path.home() / ".config/pelmeni/credentials.toml"
        )
        self._store = TomlCredentialStore(credential_path)
        self._environ = os.environ if environ is None else environ
        environment_handler = EnvVarHandler(self._environ)
        store_handler = TomlStoreHandler(self._store)
        environment_handler.set_next(store_handler).set_next(NoAuthHandler())
        self._resolver = CredentialResolver(environment_handler)

    def load(self) -> dict[str, Credentials]:  # noqa: WPS210
        """Load and validate every stored credential."""
        credentials: dict[str, Credentials] = {}
        adapter: TypeAdapter[Credentials] = TypeAdapter(Credentials)
        for provider, raw_credential in self._store.load().items():
            payload = dict(raw_credential)
            payload.setdefault("provider", provider)
            try:
                credentials[provider] = adapter.validate_python(payload)
            except ValidationError as exc:
                error_message = f"Invalid credentials for provider '{provider}'"
                raise AuthError(error_message) from exc
        return credentials

    def save(self, credentials: dict[str, Credentials]) -> None:
        """Save credentials without serializing provider names twice."""
        stored_credentials: dict[str, dict[str, Any]] = {}
        for provider, credential in credentials.items():
            payload = credential.model_dump(exclude={"provider"})
            stored_credentials[provider] = payload
        self._store.save(stored_credentials)

    def resolve(self, provider: str) -> Credentials:
        """Resolve credentials from environment, store, or no-auth rules."""
        try:
            credentials = self._resolver.resolve_credentials(provider)
        except CredentialResolutionError as exc:
            raise AuthError(str(exc)) from exc
        if credentials is None:
            error_message = (
                f"No credentials found for provider '{provider}'. "
                f"Run `pelmeni auth login {provider}`."
            )
            raise AuthError(error_message)
        return credentials

    def login(
        self,
        provider: str,
        api_key: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> Credentials:
        """Create and persist API-key, no-auth, or Google credentials."""
        if api_key is None:
            if provider != "google":
                error_message = f"Provider '{provider}' requires an API key"
                raise AuthError(error_message)
            credentials = self._google_credentials(client_id, client_secret)
        else:
            credentials = self._api_key_credentials(provider, api_key)
        stored_credentials = self.load()
        stored_credentials[provider] = credentials
        self.save(stored_credentials)
        return credentials

    @staticmethod
    def _api_key_credentials(  # noqa: WPS602
        provider: str,
        api_key: str,
    ) -> Credentials:
        normalized_key = api_key.strip()
        if not normalized_key:
            error_message = "API key must not be empty"
            raise AuthError(error_message)
        if normalized_key.lower() == "none":
            return NoCredentials(provider=provider)
        return ApiKeyCredentials(
            provider=provider,
            api_key=SecretStr(normalized_key),
        )

    def _google_credentials(
        self,
        client_id: str | None,
        client_secret: str | None,
    ) -> Credentials:
        resolved_client_id = client_id or self._environ.get("GOOGLE_CLIENT_ID")
        if not resolved_client_id:
            error_message = "Google OAuth requires a client ID"
            raise AuthError(error_message)
        try:
            return GoogleOAuthFlow(
                resolved_client_id,
                client_secret or self._environ.get("GOOGLE_CLIENT_SECRET"),
            ).login()
        except RuntimeError as exc:
            error_message = f"Google OAuth login failed: {exc}"
            raise AuthError(error_message) from exc

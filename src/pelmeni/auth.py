"""Auth module for pelmeni: credential models, storage, OAuth, login.

No agent SDKs. Python 3.14. Raw httpx + Pydantic. 80-column limit.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pelmeni._auth_codec import CredentialCodec
from pelmeni._auth_login import AuthLoginService, LoginOptions
from pelmeni._auth_oauth import OAuthFlowHandler
from pelmeni._auth_resolver import AuthDependencies, CredentialResolver
from pelmeni._auth_store import AuthTokenStore
from pelmeni.credentials import (
    CREDENTIALS_PATH,
    Credentials,
)

if TYPE_CHECKING:
    from pathlib import Path


class AuthError(Exception):
    """Authentication or credential resolution error."""


class AuthManager:
    """Manages loading, saving, resolving, and refreshing credentials."""

    def __init__(
        self,
        path: Path = CREDENTIALS_PATH,
        environ: dict[str, str] | None = None,
        dependencies: AuthDependencies | None = None,
    ) -> None:
        """Initialize AuthManager with path, environ, and dependencies."""
        self.path = path
        self.environ = os.environ if environ is None else environ
        if dependencies is None:
            codec = CredentialCodec()
            store = AuthTokenStore(self.path, AuthError)
            oauth = OAuthFlowHandler(AuthError, codec=codec)
            dependencies = AuthDependencies(
                error_cls=AuthError, codec=codec, store=store, oauth=oauth
            )
        self._deps = dependencies
        self._codec = dependencies.codec
        self._store = dependencies.store
        self._oauth = dependencies.oauth
        self._resolver = CredentialResolver(
            path=self.path,
            environ=self.environ,
            dependencies=dependencies,
        )
        self._login_service = AuthLoginService(
            environ=self.environ,
            dependencies=dependencies,
        )

    def load(self) -> dict[str, Credentials]:
        """Load credentials table from TOML file."""
        credentials_table = self._store.read_data()
        return self._resolver.validate_stored_data(credentials_table)

    def save(self, credentials: dict[str, Credentials]) -> None:
        """Atomically save credentials with private permissions."""
        credentials_table: dict[str, dict[str, Any]] = {}
        for key, cred in credentials.items():
            cred_dump = cred.model_dump(exclude_none=True)
            cred_dump.pop("provider", None)
            credentials_table[key] = cred_dump

        self._store.write_data(credentials_table)

    def resolve(self, provider: str) -> Credentials:
        """Resolve credentials for provider."""
        creds_dict = self.load()
        return self._resolver.resolve(provider, creds_dict, self.save)

    def login(
        self,
        provider: str,
        api_key: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> Credentials:
        """Perform auth login for a provider and save credentials."""
        return self._login_service.login(
            provider=provider,
            options=LoginOptions(
                api_key=api_key,
                client_id=client_id,
                client_secret=client_secret,
            ),
            load_fn=self.load,
            save_fn=self.save,
        )

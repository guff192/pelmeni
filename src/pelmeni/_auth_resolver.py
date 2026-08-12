"""Credential resolution helper for pelmeni auth."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Never

from pydantic import SecretStr

from pelmeni._auth_validator import StoredCredentialValidator
from pelmeni.credentials import (
    ApiKeyCredentials,
    Credentials,
    NoCredentials,
    OAuthCredentials,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pelmeni._auth_codec import CredentialCodec
    from pelmeni._auth_oauth import OAuthFlowHandler
    from pelmeni._auth_store import AuthTokenStore
    from pelmeni.auth import AuthError

SaveCallback = Callable[[dict[str, Credentials]], None]


@dataclass(frozen=True)
class AuthDependencies:
    """Bundle of internal services for authentication and credentials."""

    error_cls: type[AuthError]
    codec: CredentialCodec
    store: AuthTokenStore
    oauth: OAuthFlowHandler


class CredentialResolver:
    """Resolves credentials and validates stored credentials table."""

    def __init__(
        self,
        path: Path,
        environ: Mapping[str, str],
        dependencies: AuthDependencies,
    ) -> None:
        """Initialize resolver with path, environ, and dependencies."""
        self.path = path
        self.environ = environ
        self._error_cls = dependencies.error_cls
        self._codec = dependencies.codec
        self._store = dependencies.store
        self._oauth = dependencies.oauth
        self._validator = StoredCredentialValidator(
            path=path,
            error_cls=dependencies.error_cls,
            codec=dependencies.codec,
        )

    def validate_stored_data(
        self, stored_credentials: dict[str, Any]
    ) -> dict[str, Credentials]:
        """Validate raw dictionary loaded from store into Credentials."""
        return self._validator.validate_stored_data(stored_credentials)

    def resolve(
        self,
        provider: str,
        creds_dict: dict[str, Credentials],
        save_cb: SaveCallback,
    ) -> Credentials:
        """Resolve credentials for provider, checking env and stored file."""
        norm = self._codec.normalize_provider(provider)
        env_cred = self._resolve_env_credentials(norm)
        if env_cred is not None:
            return env_cred

        matched_key = provider if provider in creds_dict else norm
        cred = creds_dict.get(matched_key)

        if cred is None:
            self._raise_missing_credentials_error(provider, norm)

        return self._resolve_stored_or_oauth(
            matched_key=matched_key,
            cred=cred,
            creds_dict=creds_dict,
            save_cb=save_cb,
        )

    def _resolve_env_credentials(self, norm: str) -> Credentials | None:
        """Resolve credentials from environment variable if present."""
        env_var = f"PELMENI_{norm.upper()}_API_KEY"
        env_val = self.environ.get(env_var)

        if env_val is None:
            return None

        stripped = env_val.strip()
        if not stripped:
            msg = (
                f"Environment variable {env_var} is empty. "
                "Set a valid API key or unset the variable."
            )
            raise self._error_cls(msg)

        if stripped.lower() == "none":
            return NoCredentials()

        return ApiKeyCredentials(api_key=SecretStr(stripped))

    def _raise_missing_credentials_error(
        self, provider: str, norm: str
    ) -> Never:
        """Raise AuthError when no credentials exist for provider."""
        env_var = f"PELMENI_{norm.upper()}_API_KEY"
        msg = (
            f"No credentials found for provider '{provider}'. "
            f"Please set {env_var} or run `pelmeni auth login {provider}`."
        )
        raise self._error_cls(msg)

    def _resolve_stored_or_oauth(
        self,
        matched_key: str,
        cred: Credentials,
        creds_dict: dict[str, Credentials],
        save_cb: SaveCallback,
    ) -> Credentials:
        """Handle stored credentials, refreshing OAuth token if expired."""
        if isinstance(cred, OAuthCredentials) and cred.is_expired():
            updated_cred = self._oauth.refresh_oauth_token(matched_key, cred)
            creds_dict[matched_key] = updated_cred
            save_cb(creds_dict)
            return updated_cred

        return cred

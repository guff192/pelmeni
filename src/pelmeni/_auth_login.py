"""Login service helper for pelmeni auth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import SecretStr

from pelmeni.credentials import (
    ApiKeyCredentials,
    Credentials,
    NoCredentials,
    OAuthCredentials,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from pelmeni._auth_codec import CredentialCodec
    from pelmeni._auth_oauth import OAuthFlowHandler
    from pelmeni._auth_resolver import AuthDependencies
    from pelmeni.auth import AuthError


@dataclass(frozen=True, slots=True)
class LoginOptions:
    """Optional credentials supplied for an authentication login."""

    api_key: str | None
    client_id: str | None
    client_secret: str | None


class AuthLoginService:
    """Service handling API key and OAuth login branching."""

    def __init__(
        self,
        environ: Mapping[str, str],
        dependencies: AuthDependencies,
    ) -> None:
        """Initialize login service with environ and dependencies."""
        self._environ = environ
        self._error_cls: type[AuthError] = dependencies.error_cls
        self._codec: CredentialCodec = dependencies.codec
        self._oauth: OAuthFlowHandler = dependencies.oauth

    def login(
        self,
        provider: str,
        options: LoginOptions,
        load_fn: Callable[[], dict[str, Credentials]],
        save_fn: Callable[[dict[str, Credentials]], None],
    ) -> Credentials:
        """Perform auth login for provider and save credentials."""
        norm_provider = self._codec.normalize_provider(provider)

        if options.api_key is not None:  # noqa: WPS504
            cred = self._login_api_key(provider, options.api_key)
        elif norm_provider == "google":
            cred = self._login_google_oauth(options)
        else:
            self._raise_login_error(provider, norm_provider)

        existing_creds = load_fn()
        existing_creds[provider] = cred
        save_fn(existing_creds)
        return cred

    def _login_google_oauth(
        self,
        options: LoginOptions,
    ) -> OAuthCredentials:
        client_id = options.client_id or self._environ.get("GOOGLE_CLIENT_ID")
        client_secret = options.client_secret or self._environ.get(
            "GOOGLE_CLIENT_SECRET"
        )
        if not client_id:
            msg = (
                "Google OAuth login requires client_id "
                "(pass --client-id or set GOOGLE_CLIENT_ID)"
            )
            raise self._error_cls(msg)
        return self._oauth.device_login_google(
            client_id=client_id,
            client_secret=client_secret,
        )

    def _login_api_key(self, provider: str, api_key: str) -> Credentials:
        key_str = api_key.strip()
        if not key_str:
            msg = f"Provided API key for provider '{provider}' is empty."
            raise self._error_cls(msg)

        if key_str.lower() == "none":
            return NoCredentials()
        return ApiKeyCredentials(api_key=SecretStr(key_str))

    def _raise_login_error(self, provider: str, norm_provider: str) -> None:
        if norm_provider in ("openai", "anthropic"):
            msg = (
                f"Provider '{provider}' does not support OAuth device flow "
                "login. Please supply an API key (e.g. `pelmeni auth login "
                f"{provider} --api-key KEY`)."
            )
            raise self._error_cls(msg)
        if norm_provider in ("ollama", "lmstudio", "openai_compatible"):
            env_name = f"PELMENI_{norm_provider.upper()}_API_KEY"
            msg = (
                f"Provider '{provider}' requires an API key or explicit 'none'"
                ". Pass api_key parameter or set environment variable "
                f"{env_name}."
            )
            raise self._error_cls(msg)

        msg = (
            f"Provider '{provider}' is unrecognized or does not support "
            "OAuth. Please supply an API key or 'none'."
        )
        raise self._error_cls(msg)

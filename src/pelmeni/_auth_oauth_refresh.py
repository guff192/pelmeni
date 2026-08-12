"""OAuth token refresh handling for pelmeni auth module."""

from __future__ import annotations

import time

from pydantic import SecretStr

from pelmeni._auth_codec import CredentialCodec
from pelmeni.credentials import OAuthCredentials
from pelmeni.oauth import GoogleOAuthClient, GoogleTokenResponse


class OAuthTokenRefresher:
    """Handles OAuth 2.0 token refreshing."""

    def __init__(
        self,
        error_cls: type[Exception],
        codec: CredentialCodec | None = None,
    ) -> None:
        """Initialize OAuthTokenRefresher."""
        self.error_cls = error_cls
        self.codec = CredentialCodec() if codec is None else codec

    def refresh_oauth_token(
        self,
        provider_key: str,
        cred: OAuthCredentials,
    ) -> OAuthCredentials:
        """Refresh expired OAuth token."""
        self._validate_provider(provider_key)
        rf_token = self._get_refresh_token(provider_key, cred)
        res = self._refresh_google(provider_key, cred, rf_token)
        return self._replace_credentials(cred, res, rf_token)

    def _validate_provider(self, provider_key: str) -> None:
        norm = self.codec.normalize_provider(provider_key)
        if norm == "google":
            return
        msg = (
            "OAuth token refresh is not supported for provider "
            f"'{provider_key}'."
        )
        raise self.error_cls(msg)

    def _get_refresh_token(
        self, provider_key: str, cred: OAuthCredentials
    ) -> str:
        if cred.refresh_token:
            return cred.refresh_token.get_secret_value()
        msg = (
            f"OAuth credential for '{provider_key}' lacks a refresh token. "
            "Please log in again."
        )
        raise self.error_cls(msg)

    def _refresh_google(
        self,
        provider_key: str,
        cred: OAuthCredentials,
        refresh_token_str: str,
    ) -> GoogleTokenResponse:
        secret_val = (
            cred.client_secret.get_secret_value()
            if cred.client_secret
            else None
        )
        client = GoogleOAuthClient(
            client_id=cred.client_id, client_secret=secret_val
        )
        try:
            return client.refresh(refresh_token=refresh_token_str)
        except RuntimeError as exc:
            msg = (
                f"OAuth token refresh failed for provider '{provider_key}': "
                f"{exc}"
            )
            raise self.error_cls(msg) from exc

    def _replace_credentials(
        self,
        cred: OAuthCredentials,
        res: GoogleTokenResponse,
        fallback_refresh: str,
    ) -> OAuthCredentials:
        new_refresh = res.refresh_token or fallback_refresh
        new_expires_at = time.time() + res.expires_in
        return OAuthCredentials(
            access_token=SecretStr(res.access_token),
            refresh_token=SecretStr(new_refresh),
            expires_at=new_expires_at,
            client_id=cred.client_id,
            client_secret=cred.client_secret,
            token_type=res.token_type,
        )

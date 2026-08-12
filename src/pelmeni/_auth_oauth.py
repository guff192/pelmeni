"""OAuth flow handling for pelmeni auth module."""

from __future__ import annotations

import time

from pydantic import SecretStr

from pelmeni._auth_codec import CredentialCodec
from pelmeni._auth_oauth_refresh import OAuthTokenRefresher
from pelmeni.credentials import OAuthCredentials
from pelmeni.oauth import GoogleOAuthClient


class OAuthFlowHandler:
    """Handles OAuth 2.0 device flow and token refreshing."""

    def __init__(
        self,
        error_cls: type[Exception],
        codec: CredentialCodec | None = None,
    ) -> None:
        """Initialize OAuthFlowHandler."""
        self.error_cls = error_cls
        self.codec = CredentialCodec() if codec is None else codec
        self.refresher = OAuthTokenRefresher(
            error_cls=error_cls, codec=self.codec
        )

    def device_login_google(
        self,
        client_id: str,
        client_secret: str | None = None,
    ) -> OAuthCredentials:
        """Perform Google OAuth device flow login."""
        client = GoogleOAuthClient(
            client_id=client_id, client_secret=client_secret
        )
        try:
            token_res = client.device_login()
        except RuntimeError as exc:
            msg = f"Google device authorization failed: {exc}"
            raise self.error_cls(msg) from exc

        refresh_token = (
            SecretStr(token_res.refresh_token)
            if token_res.refresh_token
            else None
        )

        return OAuthCredentials(
            access_token=SecretStr(token_res.access_token),
            refresh_token=refresh_token,
            expires_at=time.time() + token_res.expires_in,
            client_id=client_id,
            client_secret=SecretStr(client_secret) if client_secret else None,
            token_type=token_res.token_type,
        )

    def refresh_oauth_token(
        self,
        provider_key: str,
        cred: OAuthCredentials,
    ) -> OAuthCredentials:
        """Refresh expired OAuth token."""
        return self.refresher.refresh_oauth_token(provider_key, cred)

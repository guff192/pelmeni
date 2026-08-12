"""OAuth 2.0 device authorization and token refresh implementation for Google.

No agent SDKs. Python 3.14. Raw httpx + Pydantic. 80-column limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pelmeni._oauth_exchange import (
    GoogleDeviceCodeResponse,
    GoogleTokenResponse,
    OAuthTokenExchange,
)
from pelmeni._oauth_poll import OAuthDevicePoller

if TYPE_CHECKING:
    from collections.abc import Callable


class GoogleOAuthClient:
    """Client for Google OAuth 2.0 device flow and token refresh operations."""

    def __init__(
        self, client_id: str, client_secret: str | None = None
    ) -> None:
        """Initialize Google OAuth client with credentials."""
        self.exchange = OAuthTokenExchange(
            client_id=client_id, client_secret=client_secret
        )
        self.poller = OAuthDevicePoller(exchange=self.exchange)

    def device_login(
        self,
        print_fn: Callable[[str], None] | None = print,
    ) -> GoogleTokenResponse:
        """Initiate device login flow, prompt user, poll, and return tokens."""
        code_res = self.initiate_device_flow()
        if print_fn is not None:
            print_fn(
                f"\n1. Open: {code_res.verification_url}\n"
                f"2. Enter code: {code_res.user_code}\n"
                "Waiting for authorization..."
            )
        return self.poll_device_token(
            device_code=code_res.device_code,
            expires_in=code_res.expires_in,
            interval=code_res.interval,
        )

    def refresh(self, refresh_token: str) -> GoogleTokenResponse:
        """Refresh Google OAuth access token using refresh token."""
        return self.exchange.refresh(refresh_token=refresh_token)

    def initiate_device_flow(self) -> GoogleDeviceCodeResponse:
        """Initiate device authorization request."""
        return self.exchange.initiate_device_flow()

    def poll_device_token(
        self,
        device_code: str,
        expires_in: int,
        interval: int,
    ) -> GoogleTokenResponse:
        """Poll token endpoint until token granted or flow expired."""
        return self.poller.poll(
            device_code=device_code,
            expires_in=expires_in,
            interval=interval,
        )


def initiate_google_device_flow(
    client_id: str,
    client_secret: str | None = None,
) -> GoogleDeviceCodeResponse:
    """Initiate Google OAuth 2.0 Device Flow."""
    client = GoogleOAuthClient(
        client_id=client_id, client_secret=client_secret
    )
    return client.initiate_device_flow()


def poll_google_device_token(
    client_id: str,
    device_code: str,
    expires_in: int,
    interval: int = 5,
    client_secret: str | None = None,
) -> GoogleTokenResponse:
    """Poll Google OAuth 2.0 token endpoint until granted or expired."""
    client = GoogleOAuthClient(
        client_id=client_id, client_secret=client_secret
    )
    return client.poll_device_token(
        device_code=device_code,
        expires_in=expires_in,
        interval=interval,
    )


def refresh_google_oauth_token(
    client_id: str,
    refresh_token: str,
    client_secret: str | None = None,
) -> GoogleTokenResponse:
    """Refresh Google OAuth access token using refresh_token."""
    client = GoogleOAuthClient(
        client_id=client_id, client_secret=client_secret
    )
    return client.refresh(refresh_token=refresh_token)

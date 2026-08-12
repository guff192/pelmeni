"""OAuth device flow polling collaborator.

No agent SDKs. Python 3.14. Raw httpx + Pydantic. 80-column limit.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pelmeni._oauth_exchange import (
        GoogleTokenResponse,
        OAuthTokenExchange,
    )

from pelmeni._oauth_exchange import HTTP_STATUS_OK

DEFAULT_SLOW_DOWN_EXTRA_SECONDS = 5


class OAuthDevicePoller:
    """Collaborator running device token polling loop and deadline control."""

    def __init__(self, exchange: OAuthTokenExchange) -> None:
        """Initialize poller with token exchange collaborator."""
        self.exchange = exchange

    def poll(
        self,
        device_code: str,
        expires_in: int,
        interval: int,
    ) -> GoogleTokenResponse:
        """Poll token endpoint until token granted or flow expired."""
        start_time = time.time()
        current_interval = interval

        while time.time() - start_time < expires_in:
            status_code, raw_data = self.exchange.request_single_poll(
                device_code
            )

            if status_code == HTTP_STATUS_OK:
                return self.exchange.parse_token_response(raw_data)

            current_interval = self._handle_poll_error(
                raw_data, current_interval
            )

        msg = "Device flow timed out."
        raise RuntimeError(msg)

    def _handle_poll_error(
        self, raw_data: object, current_interval: int
    ) -> int:
        """Process non-200 poll error body or update interval."""
        error = raw_data.get("error") if isinstance(raw_data, dict) else None
        if error == "authorization_pending":
            return current_interval
        if error == "slow_down":
            return current_interval + DEFAULT_SLOW_DOWN_EXTRA_SECONDS
        if error == "access_denied":
            msg = "Access denied by user."
            raise RuntimeError(msg)
        if error == "expired_token":
            msg = "Device code expired. Please restart login."
            raise RuntimeError(msg)

        err_desc = (
            raw_data.get("error_description", error)
            if isinstance(raw_data, dict)
            else "Unknown OAuth error"
        )
        msg = f"Google OAuth error: {err_desc}"
        raise RuntimeError(msg)

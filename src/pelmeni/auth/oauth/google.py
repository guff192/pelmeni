"""Google OAuth device flow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import SecretStr

from pelmeni.auth.oauth.flow import OAuthFlow
from pelmeni.dto.credentials import OAuthCredentials

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class GoogleDeviceCodeResponse:
    """Google device authorization response."""

    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


@dataclass(frozen=True, slots=True)
class GoogleTokenResponse:
    """Google OAuth token response."""

    access_token: str
    expires_in: int
    refresh_token: str | None = None


class GoogleOAuthClient:  # noqa: WPS214
    """Client for Google OAuth device and refresh operations."""

    _DEVICE_URL = "https://oauth2.googleapis.com/device/code"  # noqa: WPS115
    _TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105, WPS115
    _SCOPE = "https://www.googleapis.com/auth/cloud-platform"  # noqa: WPS115

    def __init__(
        self,
        client_id: str,
        client_secret: str | None = None,
    ) -> None:
        """Initialize the Google OAuth client."""
        self._client_id = client_id
        self._client_secret = client_secret

    def device_login(
        self,
        print_fn: Callable[[str], None] | None = print,
    ) -> GoogleTokenResponse:
        """Prompt for authorization and poll for an OAuth token."""
        code_response = self.initiate_device_flow()
        if print_fn is not None:
            print_fn(
                f"\n1. Open: {code_response.verification_url}\n"
                f"2. Enter code: {code_response.user_code}\n"
                "Waiting for authorization...",
            )
        return self.poll_device_token(
            device_code=code_response.device_code,
            expires_in=code_response.expires_in,
            interval=code_response.interval,
        )

    def refresh(self, refresh_token: str) -> GoogleTokenResponse:
        """Refresh an OAuth token."""
        payload = self._client_payload()
        payload.update(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        response_data = self._post(self._TOKEN_URL, payload)
        return self._token_response(response_data)

    def initiate_device_flow(self) -> GoogleDeviceCodeResponse:
        """Initiate device authorization."""
        response_data = self._post(
            self._DEVICE_URL,
            {"client_id": self._client_id, "scope": self._SCOPE},
        )
        return GoogleDeviceCodeResponse(
            device_code=str(response_data["device_code"]),
            user_code=str(response_data["user_code"]),
            verification_url=str(response_data["verification_url"]),
            expires_in=int(response_data["expires_in"]),
            interval=int(response_data.get("interval", 5)),
        )

    def poll_device_token(
        self,
        device_code: str,
        expires_in: int,
        interval: int,
    ) -> GoogleTokenResponse:
        """Poll until device authorization succeeds or expires."""
        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            response_data = self._poll(device_code)
            error_code = response_data.get("error")
            if error_code is None:
                return self._token_response(response_data)
            if error_code not in {"authorization_pending", "slow_down"}:
                error_message = str(
                    response_data.get("error_description", error_code),
                )
                raise RuntimeError(error_message)
            if error_code == "slow_down":
                interval += 5
            time.sleep(interval)
        error_message = "Google device authorization expired"
        raise RuntimeError(error_message)

    def _poll(self, device_code: str) -> dict[str, Any]:
        payload = self._client_payload()
        payload.update(
            {
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        return self._post(self._TOKEN_URL, payload, raise_for_status=False)

    def _client_payload(self) -> dict[str, str]:
        payload = {"client_id": self._client_id}
        if self._client_secret is not None:
            payload["client_secret"] = self._client_secret
        return payload

    @staticmethod
    def _post(  # noqa: WPS602
        url: str,
        payload: dict[str, str],
        *,
        raise_for_status: bool = True,
    ) -> dict[str, Any]:
        try:  # noqa: WPS229
            response = httpx.post(
                url,
                data=payload,
                timeout=30,  # noqa: WPS432
            )
            if raise_for_status:
                response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            error_message = f"Google OAuth request failed: {exc}"
            raise RuntimeError(error_message) from exc

    @staticmethod
    def _token_response(  # noqa: WPS602
        response_data: dict[str, Any],
    ) -> GoogleTokenResponse:
        return GoogleTokenResponse(
            access_token=str(response_data["access_token"]),
            expires_in=int(response_data["expires_in"]),
            refresh_token=response_data.get("refresh_token"),
        )


class GoogleOAuthFlow(OAuthFlow):
    """Adapt the Google OAuth client to authentication DTOs."""

    def __init__(
        self,
        client_id: str,
        client_secret: str | None = None,
    ) -> None:
        """Initialize the Google device flow."""
        self._client = GoogleOAuthClient(client_id, client_secret)

    def login(self) -> OAuthCredentials:
        """Run Google's device authorization flow."""
        token_response = self._client.device_login()
        if not token_response.refresh_token:
            error_message = "Google did not return a refresh token"
            raise RuntimeError(error_message)
        return self._credentials(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_in=token_response.expires_in,
        )

    def refresh(self, refresh_token: str) -> OAuthCredentials:
        """Refresh Google access credentials."""
        token_response = self._client.refresh(refresh_token)
        return self._credentials(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token or refresh_token,
            expires_in=token_response.expires_in,
        )

    @staticmethod
    def _credentials(  # noqa: WPS602
        access_token: str,
        refresh_token: str,
        expires_in: int,
    ) -> OAuthCredentials:
        return OAuthCredentials(
            provider="google",
            access_token=SecretStr(access_token),
            refresh_token=SecretStr(refresh_token),
            expires_at=int(time.time()) + expires_in,
        )

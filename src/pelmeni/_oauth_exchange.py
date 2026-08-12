"""OAuth token exchange HTTP interactions and models for Google.

No agent SDKs. Python 3.14. Raw httpx + Pydantic. 80-column limit.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field

GOOGLE_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
GOOGLE_OAUTH_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_GEMINI_SCOPE = "https://www.googleapis.com/auth/generative-language"
HTTP_STATUS_OK = 200
DEFAULT_TIMEOUT_SECONDS = 30.0
GRANT_TYPE_DEVICE_CODE = "urn:ietf:params:oauth:grant-type:device_code"
REFRESH_GRANT_TYPE = "refresh_token"


class GoogleDeviceCodeResponse(BaseModel):
    """Parsed Google device code authorization response."""

    model_config = ConfigDict(extra="ignore")

    device_code: str = Field(min_length=1)
    user_code: str = Field(min_length=1)
    verification_url: str = Field(alias="verification_url", min_length=1)
    expires_in: int = Field(gt=0)
    interval: int = Field(default=5, ge=1)


class GoogleTokenResponse(BaseModel):
    """Parsed Google OAuth token response."""

    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=1)
    expires_in: float = Field(gt=0)
    refresh_token: str | None = Field(default=None, min_length=1)
    token_type: str = Field(default="Bearer", min_length=1)


class OAuthTokenExchange:
    """Collaborator executing OAuth HTTP interactions and validation."""

    def __init__(
        self, client_id: str, client_secret: str | None = None
    ) -> None:
        """Initialize OAuth collaborator with credentials."""
        self.client_id = client_id
        self.client_secret = client_secret

    def initiate_device_flow(self) -> GoogleDeviceCodeResponse:
        """Initiate device code flow request."""
        payload: dict[str, str] = {
            "client_id": self.client_id,
            "scope": GOOGLE_GEMINI_SCOPE,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        raw_data = self._post_json(
            GOOGLE_DEVICE_CODE_URL,
            payload,
            "Failed to initiate Google device flow",
        )
        return self._parse_model(
            GoogleDeviceCodeResponse,
            raw_data,
            "Invalid Google device code response",
        )

    def request_single_poll(
        self, device_code: str
    ) -> tuple[int, object]:
        """Perform a single poll request to Google token endpoint."""
        payload: dict[str, str] = {
            "client_id": self.client_id,
            "device_code": device_code,
            "grant_type": GRANT_TYPE_DEVICE_CODE,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        try:
            resp = httpx.post(
                GOOGLE_OAUTH_ENDPOINT,
                data=payload,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            msg = f"Error polling Google token endpoint: {exc}"
            raise RuntimeError(msg) from exc
        else:
            return resp.status_code, resp.json()

    def parse_token_response(
        self, raw_data: object
    ) -> GoogleTokenResponse:
        """Validate raw token dictionary into GoogleTokenResponse."""
        return self._parse_model(
            GoogleTokenResponse, raw_data, "Invalid Google token response"
        )

    def refresh(self, refresh_token: str) -> GoogleTokenResponse:
        """Refresh Google OAuth access token."""
        payload: dict[str, str] = {
            "client_id": self.client_id,
            "grant_type": REFRESH_GRANT_TYPE,
            "refresh_token": refresh_token,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        raw_data = self._post_json(
            GOOGLE_OAUTH_ENDPOINT, payload, "Google OAuth token refresh failed"
        )
        return self._parse_model(
            GoogleTokenResponse,
            raw_data,
            "Invalid Google refresh token response",
        )

    def _post_json(
        self, url: str, payload: dict[str, str], error_prefix: str
    ) -> object:
        """Execute HTTP POST request and return raw JSON data."""
        try:
            resp = httpx.post(
                url, data=payload, timeout=DEFAULT_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            msg = f"{error_prefix}: {exc}"
            raise RuntimeError(msg) from exc
        else:
            resp.raise_for_status()
            return resp.json()

    def _parse_model[ModelT: BaseModel](
        self, model_cls: type[ModelT], raw_data: object, error_prefix: str
    ) -> ModelT:
        """Validate raw data into Pydantic model."""
        try:
            res = model_cls.model_validate(raw_data)
        except Exception as exc:
            msg = f"{error_prefix}: {exc}"
            raise RuntimeError(msg) from exc
        else:
            return res

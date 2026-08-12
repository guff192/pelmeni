"""Google Gemini provider implementation using raw httpx."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import httpx

from pelmeni.dto.credentials import ApiKeyCredentials, OAuthCredentials
from pelmeni.providers.base import (
    DEFAULT_TIMEOUT,
    ProviderCredentials,
    ProviderError,
    handle_http_errors,
)
from pelmeni.providers.google.formatters import (
    GoogleRequestTranslator,
    GoogleResponseParser,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_PROVIDER_NAME = "Google provider"


class GoogleProvider:
    """Google Gemini provider class implementing Provider protocol."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize Google Gemini provider instance."""
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._request_translator = GoogleRequestTranslator()
        self._response_parser = GoogleResponseParser()

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        model: str,
        credentials: ProviderCredentials,
    ) -> dict[str, Any]:
        """Send chat request to Google Gemini API and return OpenAI response."""
        hdr_map, qry_params = self._resolve_auth(credentials)
        payload = self._request_translator.build_payload(messages, tools)
        url = f"{self.base_url}/models/{model}:generateContent"
        resp_dict = self._send_request(url, hdr_map, qry_params, payload)
        try:
            return self._response_parser.parse_response_data(resp_dict)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

    def _send_request(
        self,
        url: str,
        headers: dict[str, str],
        request_params: dict[str, str],
        json_data: dict[str, Any],
    ) -> dict[str, Any]:
        with handle_http_errors(_PROVIDER_NAME):
            resp = httpx.post(
                url,
                headers=headers,
                params=request_params,
                json=json_data,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return cast("dict[str, Any]", resp.json())

    def _resolve_auth(
        self,
        credentials: ProviderCredentials,
    ) -> tuple[dict[str, str], dict[str, str]]:
        hdr_map: dict[str, str] = {"Content-Type": "application/json"}
        qry_params: dict[str, str] = {}
        if isinstance(credentials, ApiKeyCredentials):
            key_val = credentials.api_key.get_secret_value()
            qry_params["key"] = key_val
            hdr_map["x-goog-api-key"] = key_val
        elif isinstance(credentials, OAuthCredentials):
            token_val = credentials.access_token.get_secret_value()
            hdr_map["Authorization"] = f"Bearer {token_val}"
        else:
            message = "Google provider requires authentication."
            raise ProviderError(message)
        return hdr_map, qry_params

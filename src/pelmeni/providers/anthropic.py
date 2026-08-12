"""Anthropic LLM provider implementation using raw httpx.

Translates canonical OpenAI messages, tools, and responses to/from the
Anthropic Messages API (/v1/messages).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from pelmeni.credentials import ApiKeyCredentials, OAuthCredentials
from pelmeni.providers._anthropic_request import AnthropicRequestTranslator
from pelmeni.providers._anthropic_response import AnthropicResponseTranslator
from pelmeni.providers.base import (
    DEFAULT_TIMEOUT,
    Provider,
    ProviderCredentials,
    ProviderError,
    handle_http_errors,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com"


class AnthropicProvider(Provider):
    """Anthropic LLM provider using raw httpx."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize provider with optional base URL."""
        root = base_url.rstrip("/") if base_url else DEFAULT_BASE_URL
        self.base_url = root
        self._request_translator = AnthropicRequestTranslator()
        self._response_translator = AnthropicResponseTranslator()

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        model: str,
        credentials: ProviderCredentials,
    ) -> dict[str, Any]:
        """Send chat request to Anthropic API and return OpenAI dict."""
        api_key = self._extract_api_key(credentials)
        api_url = f"{self.base_url}/v1/messages"

        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        payload = self._request_translator.build_payload(messages, tools, model)

        with handle_http_errors("anthropic"):
            resp = httpx.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return self._response_translator.translate(resp.json())

    def _extract_api_key(
        self,
        credentials: ProviderCredentials,
    ) -> str:
        """Extract API key from validated credentials or raise ProviderError."""
        if isinstance(credentials, ApiKeyCredentials) and (
            credentials.api_key
        ):
            return credentials.api_key.get_secret_value()
        if isinstance(credentials, OAuthCredentials) and (
            credentials.access_token
        ):
            return credentials.access_token.get_secret_value()
        msg = "Anthropic provider requires an API key in credentials"
        raise ProviderError(msg)

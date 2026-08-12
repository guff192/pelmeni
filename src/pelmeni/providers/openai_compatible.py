"""OpenAI-compatible LLM provider client.

Sends raw-httpx POST to custom OpenAI-compatible /chat/completions endpoint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from pelmeni.providers.base import (
    DEFAULT_TIMEOUT,
    ProviderError,
    handle_http_errors,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pelmeni.credentials import Credentials


class OpenAICompatibleProvider:
    """OpenAI-compatible LLM provider implementation."""

    def __init__(
        self,
        base_url: str | None = None,
        provider_name: str = "OpenAI-compatible",
    ) -> None:
        """Initialize provider with optional base URL and label."""
        self.base_url = base_url
        self.provider_name = provider_name

    def chat(
        self,
        messages: list[dict],
        tools: Sequence[dict] | None,
        model: str,
        credentials: Credentials | None,
    ) -> dict:
        """Send chat completion request to an OpenAI-compatible API endpoint.

        Args:
            messages: Canonical OpenAI-formatted chat messages.
            tools: Sequence of tool specifications or None.
            model: Target model string identifier.
            credentials: Auth credentials object or None.

        Returns:
            Canonical OpenAI response dictionary.

        Raises:
            ProviderError: On missing base_url, HTTP error, timeout, network
                error, or invalid JSON response.

        """
        payload, headers, target_url = self._prepare_request_parts(
            messages,
            tools,
            model,
            credentials,
        )

        with handle_http_errors(self.provider_name):
            response_obj = httpx.post(
                target_url,
                json=payload,
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
            response_obj.raise_for_status()
            response_data = response_obj.json()

        return self._validate_response_data(response_data)

    def _prepare_request_parts(
        self,
        messages: list[dict],
        tools: Sequence[dict] | None,
        model: str,
        credentials: Credentials | None,
    ) -> tuple[dict, dict[str, str], str]:
        """Build payload, headers, and target URL for chat completion."""
        if not self.base_url:
            msg = (
                f"{self.provider_name} provider requires a base_url parameter."
            )
            raise ProviderError(msg)

        target_base_url = self.base_url.rstrip("/")
        target_url = f"{target_base_url}/chat/completions"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        headers.update(self._extract_auth_header(credentials))

        payload: dict = {
            "model": model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = list(tools)

        return payload, headers, target_url

    def _extract_auth_header(
        self,
        credentials: Credentials | None,
    ) -> dict[str, str]:
        """Extract Authorization header from credentials if present."""
        if credentials is None:
            return {}

        api_key = getattr(credentials, "api_key", None)
        if not api_key:
            api_key = getattr(credentials, "access_token", None)
        if not api_key:
            api_key = getattr(credentials, "token", None)

        if api_key is not None and hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()

        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return {}

    def _validate_response_data(self, response_payload: object) -> dict:
        """Validate canonical OpenAI chat completion response shape."""
        if not isinstance(response_payload, dict):
            msg = (
                f"{self.provider_name} response malformed: root must be a dict"
            )
            raise ProviderError(msg)

        choices = response_payload.get("choices")
        if not isinstance(choices, list):
            msg = (
                f"{self.provider_name} response malformed: "
                "missing choices list"
            )
            raise ProviderError(msg)

        return response_payload

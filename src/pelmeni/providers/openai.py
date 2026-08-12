"""OpenAI LLM provider client.

Sends raw-httpx POST to OpenAI's official /chat/completions endpoint.
"""

from __future__ import annotations

from pelmeni.providers.openai_compatible import OpenAICompatibleProvider

OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(OpenAICompatibleProvider):
    """Official OpenAI LLM provider client."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize OpenAI provider with base URL default."""
        super().__init__(
            base_url=base_url or OPENAI_BASE_URL,
            provider_name="OpenAI",
        )

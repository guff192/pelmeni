"""Factory collaborator for instantiating provider implementations."""

from __future__ import annotations

from pelmeni.providers.anthropic import AnthropicProvider
from pelmeni.providers.base import Provider, ProviderError
from pelmeni.providers.google import GoogleProvider
from pelmeni.providers.openai import OpenAIProvider
from pelmeni.providers.openai_compatible import OpenAICompatibleProvider

_COMPATIBLE_PROVIDERS = (
    "ollama",
    "lmstudio",
    "openai_compatible",
    "openai-compatible",
)


class ProviderFactory:
    """Factory for creating Provider instances based on provider name."""

    def create(self, name: str, base_url: str | None = None) -> Provider:
        """Create and return a Provider instance for the given provider name."""
        if name == "openai":
            return OpenAIProvider(base_url=base_url)
        if name == "anthropic":
            return AnthropicProvider(base_url=base_url)
        if name == "google":
            return GoogleProvider(base_url=base_url)
        if name in _COMPATIBLE_PROVIDERS:
            return OpenAICompatibleProvider(
                base_url=base_url,
                provider_name=name,
            )
        msg = f"Unknown or unsupported provider '{name}'"
        raise ProviderError(msg)

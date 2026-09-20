"""LLM provider implementations and routing facade."""

from pelmeni.providers.anthropic import AnthropicProvider  # noqa: F401
from pelmeni.providers.antigravity import AntigravityProvider  # noqa: F401
from pelmeni.providers.base import Provider, ProviderError  # noqa: F401
from pelmeni.providers.factory import ProviderFactory  # noqa: F401
from pelmeni.providers.google import GoogleProvider  # noqa: F401
from pelmeni.providers.openai import OpenAIProvider  # noqa: F401
from pelmeni.providers.openai_compatible import (  # noqa: F401
    OpenAICompatibleProvider,
)
from pelmeni.providers.router import (  # noqa: F401
    ProviderRouter,
    chat,
    configure,
    describe,
    get_configured_model,
)

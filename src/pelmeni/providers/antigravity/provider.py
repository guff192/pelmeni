"""Antigravity CLI provider for OpenAI-shaped chat requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pelmeni.providers.antigravity import events, process
from pelmeni.providers.base import Provider, ProviderCredentials, ProviderError

if TYPE_CHECKING:
    from collections.abc import Sequence


class AntigravityProvider(Provider):
    """Run chat requests through the locally authenticated agy CLI."""

    def chat(
        self,
        messages: list[dict],
        tools: Sequence[dict] | None,
        model: str,
        credentials: ProviderCredentials,
        conversation_id: str | None = None,
    ) -> dict:
        """Return assistant text from user and assistant message history.

        Authentication and tools use local CLI settings.
        Resume an existing conversation when its identifier is supplied.

        Args:
            messages: User and assistant message history.
            tools: Protocol tools validated before using local CLI settings.
            model: Required non-empty protocol model identifier.
            credentials: Protocol credentials validated before local CLI use.
            conversation_id: Existing conversation identifier to resume.

        Returns:
            OpenAI-shaped response containing the assistant text.

        """
        self._validate_parameters(tools, model, credentials)
        prompt_parts = []
        for message in messages:
            message_text = message.get("content")
            if message.get("role") in {"user", "assistant"} and isinstance(
                message_text,
                str,
            ):
                prompt_parts.append(message_text)
        prompt = "\n".join(prompt_parts)
        stdout = process.run_antigravity(
            prompt,
            conversation_id=conversation_id,
        )
        return events.parse_antigravity_output(stdout)

    def _validate_parameters(
        self,
        tools: Sequence[dict] | None,
        model: str,
        credentials: ProviderCredentials,
    ) -> None:
        """Validate protocol parameters for the Antigravity provider."""
        if tools is not None and not isinstance(tools, (list, tuple)):
            msg = "Tools must be a sequence or None"
            raise ProviderError(msg)
        if credentials is not None and not hasattr(credentials, "provider"):
            msg = "Invalid provider credentials"
            raise ProviderError(msg)
        if not model:
            msg = "Model must be a non-empty string"
            raise ProviderError(msg)

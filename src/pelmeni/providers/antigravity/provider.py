"""Antigravity CLI provider for OpenAI chat with persistent sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from pelmeni.providers.antigravity import process
from pelmeni.providers.base import Provider, ProviderCredentials, ProviderError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType


class AntigravityProvider(Provider):
    """Run chat requests through the locally authenticated agy CLI session."""

    def __init__(
        self, session: process.AntigravitySession | None = None
    ) -> None:
        """Initialize Antigravity provider with persistent session."""
        self._session = session
        self._conversation_id: str | None = None

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
        if conversation_id is not None:
            self._conversation_id = conversation_id

        prompt = self._extract_prompt(messages)

        if self._session is None or not self._session.is_running():
            self._session = process.AntigravitySession(
                model=model,
                conversation_id=self._conversation_id,
            )

        response_text = self._session.send_prompt(prompt)
        if self._session.conversation_id:
            self._conversation_id = self._session.conversation_id

        return {
            "choices": [
                {"message": {"role": "assistant", "content": response_text}},
            ],
        }

    def close(self) -> None:
        """Close the underlying session if active."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> Self:
        """Enter provider context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit provider context manager."""
        self.close()

    def _extract_prompt(self, messages: list[dict]) -> str:
        """Extract prompt text from messages history."""
        prompt_parts = []
        for message in messages:
            message_text = message.get("content")
            if message.get("role") in {"user", "assistant"} and isinstance(
                message_text,
                str,
            ):
                prompt_parts.append(message_text)
        return "\n".join(prompt_parts)

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

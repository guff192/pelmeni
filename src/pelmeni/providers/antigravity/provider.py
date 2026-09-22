"""Antigravity CLI provider for OpenAI chat with persistent sessions."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, ClassVar, Self

from pelmeni.providers.antigravity import process
from pelmeni.providers.base import Provider, ProviderCredentials, ProviderError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType


def _build_policy_prompt(
    role: str,
    tools: Sequence[dict] | None,
    base_prompt: str,
) -> str:
    """Build tool routing system policy header."""
    tool_names = [
        spec["function"]["name"]
        for spec in (tools or [])
        if "function" in spec and "name" in spec["function"]
    ]
    if tool_names:
        tools_str = ", ".join(tool_names)
        clause = f"Available tools for role '{role}': {tools_str}."
    else:
        clause = f"Permitted tools are restricted to role '{role}'."

    instruction = (
        "[SYSTEM POLICY]\n"
        "Do NOT run shell commands or edit files directly.\n"
        "Route all tool requests through the 'pelmeni' MCP server.\n"
        f"{clause}\n"
        "[/SYSTEM POLICY]\n\n"
    )
    return f"{instruction}{base_prompt}"


DEFAULT_ANTIGRAVITY_MODEL = "gemini-3.8-flash-low"
SUPPORTED_ANTIGRAVITY_MODELS = (
    "gemini-3.8-flash-low",
    "gemini-3.8-flash-medium",
    "gemini-3.8-flash-high",
    "gemini-3.7-flash-low",
    "gemini-3.7-flash-medium",
    "gemini-3.7-flash-high",
    "gemini-3.1-pro-low",
    "gemini-3.1-pro-high",
)


class AntigravityProvider(Provider):
    """Run chat requests through the locally authenticated agy CLI session."""

    tools: ClassVar[list[str]] = []

    def __init__(
        self,
        session: process.AntigravitySession | None = None,
        role: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize Antigravity provider with persistent session."""
        self._session = session
        self._role = role
        self._session_id = session_id
        self._conversation_id: str | None = None

    @classmethod
    def fetch_agy_tools(cls) -> list[str]:
        """Fetch available agy tools dynamically and cache in class variable."""
        if cls.tools:
            return cls.tools
        with contextlib.suppress(Exception):
            temp_session = process.AntigravitySession()
            temp_session.send_prompt("")
            if temp_session.tools:
                cls.tools = list(temp_session.tools)
            temp_session.close()
        return cls.tools

    @property
    def session(self) -> process.AntigravitySession | None:
        """Return the underlying AntigravitySession instance."""
        return self._session

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

        prompt = self._extract_prompt(messages, tools)
        if self._session is None or not self._session.is_running():
            self._session = process.AntigravitySession(
                model=model,
                conversation_id=self._conversation_id,
                role=self._role,
                session_id=self._session_id,
            )
        response_text = self._session.send_prompt(prompt)
        if self._session.conversation_id:
            self._conversation_id = self._session.conversation_id
        if self._session.tools:
            self.__class__.tools = list(self._session.tools)
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

    def _extract_prompt(
        self,
        messages: list[dict],
        tools: Sequence[dict] | None = None,
    ) -> str:
        """Extract prompt text and inject tool routing guidance."""
        prompt_parts = [
            msg["content"]
            for msg in messages
            if msg.get("role") in {"user", "assistant"}
            and isinstance(msg.get("content"), str)
        ]
        base_prompt = "\n".join(prompt_parts)
        if not self._role:
            return base_prompt

        return _build_policy_prompt(self._role, tools, base_prompt)

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

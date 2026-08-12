"""Anthropic API payload builder collaborator.

Translates canonical OpenAI messages and tools to the Anthropic Messages API
(/v1/messages).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pelmeni.providers._anthropic_arguments import AnthropicArgumentCodec
from pelmeni.providers._anthropic_messages import (
    AnthropicMessageTranslator,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_MAX_TOKENS = 4096
KEY_TYPE = "type"
KEY_NAME = "name"
KEY_FUNCTION = "function"
KEY_MESSAGES = "messages"
KEY_SYSTEM = "system"
KEY_MODEL = "model"
KEY_MAX_TOKENS = "max_tokens"
KEY_TOOLS = "tools"
VAL_FUNCTION = "function"


def _translate_single_tool(tool: object) -> dict[str, Any] | None:
    if not isinstance(tool, dict) or tool.get(KEY_TYPE) != VAL_FUNCTION:
        return None
    func = tool.get(KEY_FUNCTION)
    if not isinstance(func, dict):
        return None
    name = func.get(KEY_NAME)
    if not name:
        return None
    return {
        KEY_NAME: name,
        "description": func.get("description", ""),
        "input_schema": func.get(
            "parameters",
            {KEY_TYPE: "object", "properties": {}},
        ),
    }


class AnthropicRequestTranslator:
    """Translator for Anthropic chat request payloads."""

    def __init__(
        self,
        codec: AnthropicArgumentCodec | None = None,
        messages_translator: AnthropicMessageTranslator | None = None,
    ) -> None:
        """Initialize translator with injected codec and message translator."""
        self._codec = codec or AnthropicArgumentCodec()
        self._messages_translator = (
            messages_translator or AnthropicMessageTranslator(codec=self._codec)
        )

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        model: str,
    ) -> dict[str, Any]:
        """Build request payload dictionary."""
        system_prompt, formatted_messages = (
            self._messages_translator.extract_system_and_messages(messages)
        )
        payload: dict[str, Any] = {
            KEY_MODEL: model,
            KEY_MESSAGES: formatted_messages,
            KEY_MAX_TOKENS: DEFAULT_MAX_TOKENS,
        }
        if system_prompt:
            payload[KEY_SYSTEM] = system_prompt
        if tools:
            payload[KEY_TOOLS] = self.translate_tools(tools)
        return payload

    def translate_tools(
        self,
        tools: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Translate canonical OpenAI tool schemas to Anthropic tool schemas."""
        anthropic_tools: list[dict[str, Any]] = []
        for tool in tools:
            translated = _translate_single_tool(tool)
            if translated:
                anthropic_tools.append(translated)
        return anthropic_tools

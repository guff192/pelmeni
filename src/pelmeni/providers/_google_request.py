"""Google Gemini request translator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pelmeni.providers._google_messages import GoogleMessageTranslator
from pelmeni.providers._google_tools import GoogleToolTranslator

if TYPE_CHECKING:
    from collections.abc import Sequence

_KEY_CONTENTS = "contents"
_KEY_SYSTEM_INSTRUCTION = "systemInstruction"
_KEY_TOOLS = "tools"


class GoogleRequestTranslator:
    """Translator for converting standard messages to Gemini requests."""

    def __init__(
        self,
        message_translator: GoogleMessageTranslator | None = None,
        tool_translator: GoogleToolTranslator | None = None,
    ) -> None:
        self._message_translator = (
            message_translator or GoogleMessageTranslator()
        )
        self._tool_translator = (
            tool_translator or GoogleToolTranslator()
        )

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Build payload with contents, system instruction, and tools."""
        system_instruction, converted_contents = (
            self._message_translator.convert_messages(messages)
        )
        payload: dict[str, Any] = {_KEY_CONTENTS: converted_contents}
        if system_instruction:
            payload[_KEY_SYSTEM_INSTRUCTION] = system_instruction
        converted_tools = self._tool_translator.convert_tools(tools)
        if converted_tools:
            payload[_KEY_TOOLS] = converted_tools
        return payload

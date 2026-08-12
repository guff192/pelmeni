"""Google Gemini message translator."""

from __future__ import annotations

import json
from typing import Any

from pelmeni.providers._google_assistant import GoogleAssistantTranslator

_ROLE_USER = "user"
_ROLE_SYSTEM = "system"
_ROLE_ASSISTANT = "assistant"
_ROLE_TOOL = "tool"

_KEY_PARTS = "parts"
_KEY_ROLE = "role"
_KEY_TEXT = "text"
_KEY_FUNCTION_RESPONSE = "functionResponse"
_KEY_NAME = "name"
_KEY_RESPONSE = "response"
_KEY_RESULT = "result"
_KEY_TOOL_CALL_ID = "tool_call_id"
_KEY_CONTENT = "content"

_DEFAULT_TOOL_NAME = "unknown_tool"
_SystemInst = dict[str, Any] | None
_MessageList = list[dict[str, Any]]
_GeminiMessagesResult = tuple[_SystemInst, _MessageList]


def _extract_text_content(raw_content: object) -> str:
    """Extract string content or default to empty string."""
    return raw_content if isinstance(raw_content, str) else ""


class GoogleMessageTranslator:
    """Translator for standard messages to Gemini content format."""

    def __init__(
        self,
        assistant_translator: GoogleAssistantTranslator | None = None,
    ) -> None:
        """Initialize message translator with optional assistant helper."""
        self._assistant = assistant_translator or GoogleAssistantTranslator()

    def convert_tool_message_part(
        self, msg: dict[str, Any], call_id_to_name: dict[str, str]
    ) -> dict[str, Any]:
        """Convert single tool result message to a functionResponse part."""
        raw_tool_id = msg.get(_KEY_TOOL_CALL_ID)
        tool_id = raw_tool_id if isinstance(raw_tool_id, str) else ""
        fn_name = call_id_to_name.get(
            tool_id,
            tool_id or _DEFAULT_TOOL_NAME,
        )
        res_content = msg.get(_KEY_CONTENT)
        response_obj = self._parse_tool_response(res_content)

        return {
            _KEY_FUNCTION_RESPONSE: {
                _KEY_NAME: fn_name,
                _KEY_RESPONSE: response_obj,
            }
        }

    def convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> _GeminiMessagesResult:
        """Convert standard messages into system instruction and contents."""
        system_texts: list[str] = []
        message_parts: list[dict[str, Any]] = []
        call_id_to_name = self._assistant.build_call_id_map(messages)
        for msg in messages:
            self._process_message(
                msg,
                call_id_to_name,
                system_texts,
                message_parts,
            )

        return self._build_system_instruction(system_texts), message_parts

    def _process_message(
        self,
        msg: dict[str, Any],
        call_id_to_name: dict[str, str],
        system_texts: list[str],
        message_parts: list[dict[str, Any]],
    ) -> None:
        """Process a single message into system texts or message parts."""
        role = msg.get(_KEY_ROLE)
        message_part = msg.get(_KEY_CONTENT)

        if role == _ROLE_SYSTEM:
            system_texts.append(_extract_text_content(message_part))
        elif role == _ROLE_USER:
            text = _extract_text_content(message_part)
            message_parts.append(
                {_KEY_ROLE: _ROLE_USER, _KEY_PARTS: [{_KEY_TEXT: text}]}
            )
        elif role == _ROLE_ASSISTANT:
            message_parts.append(
                self._assistant.convert_assistant_message(msg)
            )
        elif role == _ROLE_TOOL:
            part = self.convert_tool_message_part(msg, call_id_to_name)
            self._append_tool_part(message_parts, part)

    def _build_system_instruction(
        self,
        system_texts: list[str],
    ) -> dict[str, Any] | None:
        """Build a Gemini system instruction from collected text."""
        if system_texts:
            return {
                _KEY_PARTS: [{_KEY_TEXT: "\n".join(system_texts)}]
            }
        return None

    def _parse_tool_response(self, res_content: object) -> dict[str, Any]:
        """Parse tool response content into dictionary."""
        if isinstance(res_content, str):
            try:
                res_json = json.loads(res_content)
            except (json.JSONDecodeError, TypeError):
                return {_KEY_RESULT: res_content}
            else:
                if isinstance(res_json, dict):
                    return res_json
                return {_KEY_RESULT: res_json}
        if isinstance(res_content, dict):
            return res_content
        return {_KEY_RESULT: res_content}

    def _append_tool_part(
        self,
        message_parts: list[dict[str, Any]],
        part: dict[str, Any],
    ) -> None:
        """Append tool message part into contents list."""
        last_parts = (
            message_parts[-1].get(_KEY_PARTS, [])
            if message_parts and message_parts[-1].get(_KEY_ROLE) == _ROLE_USER
            else []
        )
        is_tool_block = last_parts and all(
            _KEY_FUNCTION_RESPONSE in part_item for part_item in last_parts
        )
        if is_tool_block:
            message_parts[-1][_KEY_PARTS].append(part)
        else:
            message_parts.append({_KEY_ROLE: _ROLE_USER, _KEY_PARTS: [part]})

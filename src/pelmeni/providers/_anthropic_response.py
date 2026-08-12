"""Anthropic API response translator collaborator.

Translates Anthropic Messages API responses into canonical OpenAI format.
"""

from __future__ import annotations

import json
from typing import Any

KEY_ROLE = "role"
KEY_CONTENT = "content"
KEY_TYPE = "type"
KEY_TEXT = "text"
KEY_NAME = "name"
KEY_ID = "id"
KEY_FUNCTION = "function"
KEY_TOOL_CALLS = "tool_calls"
KEY_INPUT = "input"
KEY_TOOL_USE = "tool_use"
ROLE_ASSISTANT = "assistant"
VAL_FUNCTION = "function"
KEY_CHOICES = "choices"
KEY_MESSAGE = "message"
KEY_ARGUMENTS = "arguments"


class AnthropicResponseTranslator:
    """Translator for Anthropic chat API responses."""

    def translate(self, response_data: dict[str, Any]) -> dict[str, Any]:
        """Translate Anthropic API response to canonical OpenAI structure."""
        if not isinstance(response_data, dict):
            return self._build_empty_response()

        content_blocks = response_data.get(KEY_CONTENT, [])
        if not isinstance(content_blocks, list):
            content_blocks = []

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in content_blocks:
            if isinstance(block, dict):
                self._process_block(block, text_parts, tool_calls)

        return self._build_response(text_parts, tool_calls)

    def _build_empty_response(self) -> dict[str, Any]:
        """Build response structure when response_data is non-dict."""
        return {
            KEY_CHOICES: [
                {
                    KEY_MESSAGE: {
                        KEY_ROLE: ROLE_ASSISTANT,
                        KEY_CONTENT: None,
                    }
                }
            ]
        }

    def _build_response(
        self,
        text_parts: list[str],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build final choice dict from parsed text parts and tool calls."""
        combined_text = "".join(text_parts) if text_parts else None
        message: dict[str, Any] = {
            KEY_ROLE: ROLE_ASSISTANT,
            KEY_CONTENT: combined_text,
        }
        if tool_calls:
            message[KEY_TOOL_CALLS] = tool_calls
        return {KEY_CHOICES: [{KEY_MESSAGE: message}]}

    def _process_block(
        self,
        block: dict[str, Any],
        text_parts: list[str],
        tool_calls: list[dict[str, Any]],
    ) -> None:
        """Process an individual Anthropic response block."""
        block_type = block.get(KEY_TYPE)
        if block_type == KEY_TEXT:
            text_parts.append(str(block.get(KEY_TEXT, "")))
        elif block_type == KEY_TOOL_USE:
            self._process_tool_use(block, tool_calls)

    def _process_tool_use(
        self,
        block: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> None:
        """Process tool_use block into OpenAI tool call."""
        call_id = block.get(KEY_ID)
        name = block.get(KEY_NAME)
        if not (call_id and name):
            return

        args = block.get(KEY_INPUT, {})
        args_str = json.dumps(args) if isinstance(args, dict) else str(args)
        tool_calls.append(
            {
                KEY_ID: str(call_id),
                KEY_TYPE: VAL_FUNCTION,
                KEY_FUNCTION: {
                    KEY_NAME: str(name),
                    KEY_ARGUMENTS: args_str,
                },
            }
        )

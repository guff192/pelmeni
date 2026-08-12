"""Anthropic message content and block translation collaborator.

Translates canonical OpenAI system, user, assistant, and tool result messages to
Anthropic block payloads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pelmeni.providers.anthropic.arguments import AnthropicArgumentCodec

if TYPE_CHECKING:
    from collections.abc import Sequence

KEY_ROLE = "role"
KEY_CONTENT = "content"
KEY_TYPE = "type"
KEY_TEXT = "text"
KEY_NAME = "name"
KEY_ID = "id"
KEY_FUNCTION = "function"
KEY_TOOL_CALLS = "tool_calls"
KEY_INPUT = "input"
KEY_TOOL_USE_ID = "tool_use_id"
KEY_TOOL_RESULT = "tool_result"
KEY_TOOL_USE = "tool_use"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"

FormattedMessages = list[dict[str, Any]]


def _is_user_list(formatted_messages: FormattedMessages) -> bool:
    if not formatted_messages:
        return False
    if formatted_messages[-1][KEY_ROLE] != ROLE_USER:
        return False
    return isinstance(formatted_messages[-1][KEY_CONTENT], list)


def _consolidate_user_message(
    last_message: dict[str, Any],
    user_text: str,
) -> None:
    last_content = last_message[KEY_CONTENT]
    if isinstance(last_content, list):
        last_content.append({KEY_TYPE: KEY_TEXT, KEY_TEXT: user_text})
    else:
        last_message[KEY_CONTENT] = [
            {KEY_TYPE: KEY_TEXT, KEY_TEXT: str(last_content)},
            {KEY_TYPE: KEY_TEXT, KEY_TEXT: user_text},
        ]


def _build_tool_use_block(
    call: dict[str, Any], codec: AnthropicArgumentCodec
) -> dict[str, Any] | None:
    func = call.get(KEY_FUNCTION)
    if not isinstance(func, dict):
        return None
    name = func.get(KEY_NAME)
    call_id = call.get(KEY_ID)
    if name and call_id:
        return {
            KEY_TYPE: KEY_TOOL_USE,
            KEY_ID: call_id,
            KEY_NAME: name,
            KEY_INPUT: codec.parse(func.get("arguments")),
        }
    return None


def _extract_system_prompt(msg: dict[str, Any]) -> str | None:
    if msg.get(KEY_ROLE) != ROLE_SYSTEM:
        return None
    raw_sys = msg.get(KEY_CONTENT)
    sys_str = str(raw_sys) if raw_sys else ""
    return sys_str if sys_str.strip() else None


class AnthropicMessageTranslator:
    """Translator for message blocks and formatting."""

    def __init__(
        self,
        codec: AnthropicArgumentCodec | None = None,
    ) -> None:
        """Initialize translator with injected argument codec."""
        self._codec = codec or AnthropicArgumentCodec()

    def extract_system_and_messages(
        self, messages: Sequence[dict[str, Any]]
    ) -> tuple[str | None, FormattedMessages]:
        """Extract system message and format remaining messages."""
        system_prompt: str | None = None
        formatted_messages: FormattedMessages = []

        for msg in messages:
            if isinstance(msg, dict):
                sys_candidate = _extract_system_prompt(msg)
                if sys_candidate:
                    system_prompt = sys_candidate
                else:
                    self._dispatch_non_system_message(msg, formatted_messages)

        return system_prompt, formatted_messages

    def convert_assistant_message(
        self, msg: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert OpenAI assistant message to Anthropic block."""
        anthropic_content: list[dict[str, Any]] = []
        text_payload = msg.get(KEY_CONTENT)
        if text_payload:
            anthropic_content.append(
                {KEY_TYPE: KEY_TEXT, KEY_TEXT: text_payload}
            )

        self._process_tool_calls(anthropic_content, msg.get(KEY_TOOL_CALLS))

        if not anthropic_content:
            anthropic_content.append({KEY_TYPE: KEY_TEXT, KEY_TEXT: ""})

        return {KEY_ROLE: ROLE_ASSISTANT, KEY_CONTENT: anthropic_content}

    def append_user_message(
        self,
        formatted_messages: FormattedMessages,
        user_text: str,
    ) -> None:
        """Append or consolidate a text user message into formatted messages."""
        if formatted_messages and formatted_messages[-1][KEY_ROLE] == ROLE_USER:
            _consolidate_user_message(formatted_messages[-1], user_text)
        else:
            formatted_messages.append(
                {
                    KEY_ROLE: ROLE_USER,
                    KEY_CONTENT: [{KEY_TYPE: KEY_TEXT, KEY_TEXT: user_text}],
                }
            )

    def append_tool_result(
        self,
        formatted_messages: FormattedMessages,
        tool_call_id: str | None,
        result_text: str,
    ) -> None:
        """Append or consolidate a tool result block into formatted messages."""
        block = {
            KEY_TYPE: KEY_TOOL_RESULT,
            KEY_TOOL_USE_ID: tool_call_id or "",
            KEY_CONTENT: result_text,
        }
        if _is_user_list(formatted_messages):
            formatted_messages[-1][KEY_CONTENT].append(block)
        else:
            formatted_messages.append(
                {KEY_ROLE: ROLE_USER, KEY_CONTENT: [block]}
            )

    def _dispatch_non_system_message(
        self,
        msg: dict[str, Any],
        formatted_messages: FormattedMessages,
    ) -> None:
        role = msg.get(KEY_ROLE)
        if role == ROLE_USER:
            self.append_user_message(
                formatted_messages, msg.get(KEY_CONTENT) or ""
            )
        elif role == ROLE_ASSISTANT:
            formatted_messages.append(self.convert_assistant_message(msg))
        elif role == ROLE_TOOL:
            self.append_tool_result(
                formatted_messages,
                msg.get("tool_call_id"),
                msg.get(KEY_CONTENT) or "",
            )

    def _process_tool_calls(
        self,
        anthropic_content: list[dict[str, Any]],
        tool_calls: object,
    ) -> None:
        if not isinstance(tool_calls, list):
            return
        for call in tool_calls:
            if isinstance(call, dict):
                block = _build_tool_use_block(call, self._codec)
                if block:
                    anthropic_content.append(block)

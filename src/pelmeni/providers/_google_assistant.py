"""Google Gemini assistant message and argument translator."""

from __future__ import annotations

import json
from typing import Any

_KEY_NAME = "name"
_KEY_ARGS = "args"
_KEY_FUNCTION = "function"
_KEY_TOOL_CALLS = "tool_calls"
_KEY_TOOL_CALL_ID = "tool_call_id"
_KEY_ID = "id"
_KEY_ARGUMENTS = "arguments"
_KEY_CONTENT = "content"
_KEY_FUNCTION_CALL = "functionCall"
_KEY_ROLE = "role"
_KEY_PARTS = "parts"
_KEY_TEXT = "text"
_ROLE_MODEL = "model"


class GoogleAssistantTranslator:
    """Translator for Gemini assistant messages and tool call arguments."""

    def build_call_id_map(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Build mapping from call_id to function name."""
        call_id_to_name: dict[str, str] = {}
        for msg in messages:
            tool_calls = msg.get(_KEY_TOOL_CALLS)
            if isinstance(tool_calls, list):
                self._extract_call_ids(tool_calls, call_id_to_name)
        return call_id_to_name

    def parse_fn_args(self, fn_args: object) -> dict[str, Any]:
        """Parse function arguments string or dict."""
        if isinstance(fn_args, str):
            try:
                parsed = json.loads(fn_args)
            except (json.JSONDecodeError, TypeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        if isinstance(fn_args, dict):
            return fn_args
        return {}

    def convert_assistant_message(
        self, msg: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert assistant message to Gemini model format."""
        parts: list[dict[str, Any]] = []
        if msg.get(_KEY_CONTENT):
            parts.append({_KEY_TEXT: str(msg[_KEY_CONTENT])})

        tool_calls = msg.get(_KEY_TOOL_CALLS)
        if isinstance(tool_calls, list):
            parts.extend(self._convert_tool_calls_list(tool_calls))

        if not parts:
            parts = [{_KEY_TEXT: ""}]
        return {_KEY_ROLE: _ROLE_MODEL, _KEY_PARTS: parts}

    def _convert_tool_calls_list(
        self, tool_calls: list[object]
    ) -> list[dict[str, Any]]:
        """Convert list of tool call dicts to Gemini function call parts."""
        parts: list[dict[str, Any]] = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            call_part = self._convert_tool_call(tc)
            if call_part:
                parts.append(call_part)
        return parts

    def _extract_call_ids(
        self,
        tool_calls: list[object],
        call_id_to_name: dict[str, str],
    ) -> None:
        """Add valid tool call identifiers and names to the mapping."""
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get(_KEY_ID)
            fn_info = tc.get(_KEY_FUNCTION)
            if isinstance(tc_id, str) and isinstance(fn_info, dict):
                name = fn_info.get(_KEY_NAME)
                if isinstance(name, str):
                    call_id_to_name[tc_id] = name

    def _convert_tool_call(
        self, tc: dict[object, object]
    ) -> dict[str, Any] | None:
        """Convert one tool call to a Gemini function call part."""
        fn_info = tc.get(_KEY_FUNCTION)
        fn_info_dict = fn_info if isinstance(fn_info, dict) else {}
        fn_name = fn_info_dict.get(_KEY_NAME)
        fn_args = fn_info_dict.get(_KEY_ARGUMENTS, "{}")
        return {
            _KEY_FUNCTION_CALL: {
                _KEY_NAME: fn_name if isinstance(fn_name, str) else "",
                _KEY_ARGS: self.parse_fn_args(fn_args),
            }
        }

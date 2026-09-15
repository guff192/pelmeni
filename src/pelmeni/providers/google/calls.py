"""Candidate and tool call parser for Google Gemini responses."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

from pelmeni.providers.google.text import GoogleTextParser

ToolCallList = list[dict[str, Any]]
ToolCallDict = dict[str, Any]

_KEY_FUNCTION_CALL = "functionCall"
_KEY_NAME = "name"
_KEY_ARGS = "args"
_KEY_TYPE = "type"
_TYPE_FUNCTION = "function"
_KEY_FUNCTION = "function"
_KEY_ARGUMENTS = "arguments"
_KEY_ID = "id"


class GoogleCallParser:
    """Helper parser for individual tool call entries."""

    def parse_call(
        self, part: dict[str, Any], call_index: int
    ) -> dict[str, Any] | None:
        """Parse a function call part into a standard tool call if present."""
        if _KEY_FUNCTION_CALL not in part:
            return None
        fc = part[_KEY_FUNCTION_CALL]
        if not isinstance(fc, dict):
            return None
        thought_sig = (
            part.get("thoughtSignature")
            or part.get("thought_signature")
            or fc.get("thoughtSignature")
        )
        return self._build_tool_call(fc, call_index, thought_sig)

    def _build_tool_call(
        self,
        fn_call: dict[str, Any],
        call_index: int,
        thought_sig: str | None = None,
    ) -> dict[str, Any]:
        fn_name_val = fn_call.get(_KEY_NAME)
        fn_name = fn_name_val if isinstance(fn_name_val, str) else ""
        fn_args = fn_call.get(_KEY_ARGS)
        if isinstance(fn_args, dict):
            args_str = json.dumps(fn_args)
        else:
            args_str = str(fn_args)
        tc_dict: dict[str, Any] = {
            _KEY_ID: f"call_{fn_name}_{call_index}",
            _KEY_TYPE: _TYPE_FUNCTION,
            _KEY_FUNCTION: {
                _KEY_NAME: fn_name,
                _KEY_ARGUMENTS: args_str,
            },
        }
        if isinstance(thought_sig, str) and thought_sig:
            tc_dict["thought_signature"] = thought_sig
        return tc_dict


class GoogleCandidateParser:
    """Parser for Gemini response candidate parts into standard tool calls."""

    def __init__(
        self,
        text_parser: GoogleTextParser | None = None,
        call_parser: GoogleCallParser | None = None,
    ) -> None:
        """Initialize with text and call sub-parsers."""
        self._text_parser = text_parser or GoogleTextParser()
        self._call_parser = call_parser or GoogleCallParser()

    def parse_parts(
        self,
        candidate: dict[str, Any],
    ) -> tuple[str | None, ToolCallList]:
        """Parse text parts and function calls from a candidate structure."""
        parts = self._text_parser.extract_parts(candidate)
        combined_text = self._text_parser.extract_text(parts)
        return combined_text, list(self._extract_calls(parts))

    def _extract_calls(
        self,
        parts: list[dict[str, Any]],
    ) -> Iterable[ToolCallDict]:
        call_index = 0
        for part in parts:
            if _KEY_FUNCTION_CALL in part:
                call_index += 1
                tool_call = self._call_parser.parse_call(part, call_index)
                if tool_call is not None:
                    yield tool_call

"""Google response translator for Gemini responses into OpenAI format."""

from __future__ import annotations

from typing import Any

from pelmeni.providers._google_calls import (
    GoogleCandidateParser,
    ToolCallList,
)

_KEY_CANDIDATES = "candidates"
_KEY_CONTENT = "content"
_KEY_FINISH_REASON = "finishReason"
_DEFAULT_FINISH_REASON = "stop"
_KEY_CHOICES = "choices"
_KEY_INDEX = "index"
_KEY_MESSAGE = "message"
_KEY_ROLE = "role"
_ROLE_ASSISTANT = "assistant"
_KEY_TOOL_CALLS = "tool_calls"
_ERR_NO_CANDIDATES = "Google provider returned no candidates."


class GoogleResponseParser:
    """Parser for Google Gemini API responses."""

    def __init__(
        self,
        candidate_parser: (GoogleCandidateParser | None) = None,
    ) -> None:
        """Initialize parser with candidate helper."""
        self._candidate_parser = candidate_parser or GoogleCandidateParser()

    def parse_response_data(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Parse Gemini API response into OpenAI format dict."""
        cand_dict = self._extract_first_candidate(payload)
        combined_text, tool_calls = self._candidate_parser.parse_parts(
            cand_dict
        )
        return {
            _KEY_CHOICES: [
                {
                    _KEY_INDEX: 0,
                    _KEY_MESSAGE: self._build_message(
                        combined_text,
                        tool_calls,
                    ),
                    _KEY_FINISH_REASON: self._resolve_finish_reason(cand_dict),
                }
            ]
        }

    def _extract_first_candidate(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        raw_cands = payload.get(_KEY_CANDIDATES)
        cands = raw_cands if isinstance(raw_cands, list) else []
        if not cands:
            raise ValueError(_ERR_NO_CANDIDATES)
        first = cands[0]
        cand_dict = first if isinstance(first, dict) else {}
        if not cand_dict:
            raise ValueError(_ERR_NO_CANDIDATES)
        return cand_dict

    def _resolve_finish_reason(self, cand_dict: dict[str, Any]) -> str:
        """Return a valid finish reason or the default."""
        raw = cand_dict.get(_KEY_FINISH_REASON)
        return raw if isinstance(raw, str) else _DEFAULT_FINISH_REASON

    def _build_message(
        self, combined_text: str | None, tool_calls: ToolCallList
    ) -> dict[str, Any]:
        msg_obj: dict[str, Any] = {
            _KEY_ROLE: _ROLE_ASSISTANT,
            _KEY_CONTENT: combined_text,
        }
        if tool_calls:
            msg_obj[_KEY_TOOL_CALLS] = tool_calls
        return msg_obj

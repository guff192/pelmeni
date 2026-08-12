"""Text extraction helper for Google Gemini candidates."""

from __future__ import annotations

from typing import Any

_KEY_CONTENT = "content"
_KEY_PARTS = "parts"
_KEY_TEXT = "text"


class GoogleTextParser:
    """Extracts text parts and raw candidate parts from Gemini structures."""

    def extract_parts(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract valid dictionary parts from candidate structure."""
        candidate_content = candidate.get(_KEY_CONTENT)
        content_dict = (
            candidate_content if isinstance(candidate_content, dict) else {}
        )
        raw_parts = content_dict.get(_KEY_PARTS, None)
        parts = raw_parts if isinstance(raw_parts, list) else []
        return [part for part in parts if isinstance(part, dict)]

    def extract_text(self, parts: list[dict[str, Any]]) -> str | None:
        """Extract and combine text parts into a single string."""
        text_parts: list[str] = [
            part[_KEY_TEXT]
            for part in parts
            if _KEY_TEXT in part and isinstance(part[_KEY_TEXT], str)
        ]
        return "".join(text_parts) if text_parts else None

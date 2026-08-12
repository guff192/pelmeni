"""Anthropic tool argument parsing collaborator.

Parses raw arguments payloads safely for Anthropic tool calls.
"""

from __future__ import annotations

import json
from typing import Any


class AnthropicArgumentCodec:
    """Codec for Anthropic tool call arguments."""

    def parse(self, raw_arguments: object) -> dict[str, Any]:
        """Parse raw tool argument data into a dictionary safely."""
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str):
            return self._parse_json_str(raw_arguments)
        return {}

    def _parse_json_str(self, raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        else:
            return parsed if isinstance(parsed, dict) else {}

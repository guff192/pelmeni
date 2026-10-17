"""Translate Antigravity JSON event streams into chat completion responses."""

from __future__ import annotations

import json

from pelmeni.providers.base import ProviderError

INIT_EVENT = "init"
RESULT_EVENT = "result"
_EVENT_KEY = "event"


def parse_antigravity_output(raw_output: str) -> dict:
    """Extract the successful result from a line-delimited JSON event stream.

    Args:
        raw_output: Line-delimited stream-json output from the agy CLI.

    Returns:
        Standardized OpenAI-compatible response object containing choices.

    Raises:
        ProviderError: Output contains no result event or execution failed.

    """
    result_text: str | None = None
    for line in raw_output.splitlines():
        extracted = extract_result_response(line)
        if extracted is not None:
            result_text = extracted
    if result_text is None:
        message = "Antigravity produced no result event"
        raise ProviderError(message)
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": result_text},
            },
        ],
    }


def extract_init_conversation_id(raw_line: str) -> str | None:
    """Extract conversation ID from an init event line when present.

    Checks both top-level and nested `init` payload structures.

    Args:
        raw_line: One line from the command's standard output.

    Returns:
        The conversation ID string, or None if not an init event or absent.

    """
    event = _parse_line(raw_line)
    if event is None or event.get(_EVENT_KEY) != INIT_EVENT:
        return None

    conv_id = event.get("conversation_id")
    if isinstance(conv_id, str):
        return conv_id

    init_payload = event.get(INIT_EVENT)
    if isinstance(init_payload, dict):
        nested_id = init_payload.get("conversation_id")
        if isinstance(nested_id, str):
            return nested_id

    return None


def extract_init_tools(raw_line: str) -> list[str] | None:
    """Extract tools list from an init event line when present."""
    event = _parse_line(raw_line)
    if event is None or event.get(_EVENT_KEY) != INIT_EVENT:
        return None

    init_payload = event.get(INIT_EVENT)
    if isinstance(init_payload, dict):
        tools = init_payload.get("tools")
        if isinstance(tools, list) and all(
            isinstance(elem, str) for elem in tools
        ):
            return tools
    return None


def extract_result_response(raw_line: str) -> str | None:
    """Extract result response from a raw event line when present."""
    event = _parse_line(raw_line)
    if event is None or event.get(_EVENT_KEY) != RESULT_EVENT:
        return None
    event_result = event.get("result")
    if not isinstance(event_result, dict):
        return None
    return _extract_result_text(event_result)


def extract_result_usage(raw_line: str) -> dict[str, int] | None:
    """Extract usage metrics from a result event line when present."""
    event = _parse_line(raw_line)
    if event is None or event.get(_EVENT_KEY) != RESULT_EVENT:
        return None
    event_result = event.get("result")
    if not isinstance(event_result, dict):
        return None
    usage = event_result.get("usage")
    if isinstance(usage, dict):
        return usage
    return None


def _parse_line(raw_line: str) -> dict | None:
    """Decode a JSON event, ignoring malformed or non-object lines.

    Args:
        raw_line: One line from the command's standard output.

    Returns:
        The decoded event dictionary, or None for an invalid line.

    """
    try:
        event = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if isinstance(event, dict):
        return event
    return None


def _extract_result_text(event_result: dict) -> str:
    """Validate a result and extract its response text.

    Args:
        event_result: Result payload from an Antigravity event.

    Returns:
        Response text, or an empty string when no text exists.

    Raises:
        ProviderError: The result status is not successful.

    """
    status = event_result.get("status")
    if status != "SUCCESS":
        message = f"Antigravity execution failed: {status}"
        raise ProviderError(message)
    response = event_result.get("response", event_result.get("text"))
    if isinstance(response, str):
        return response
    return ""

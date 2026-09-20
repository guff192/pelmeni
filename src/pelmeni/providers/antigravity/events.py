"""Translate Antigravity JSON event streams into chat completion responses."""

import json

from pelmeni.providers.base import ProviderError


def parse_antigravity_output(raw_output: str) -> dict:
    """Extract the successful result from a line-delimited JSON event stream.

    Args:
        raw_output: Antigravity standard output containing JSON events.

    Returns:
        An OpenAI-shaped assistant message containing the result text.

    Raises:
        ProviderError: A result reports failure or no valid result exists.

    """
    result_text: str | None = None
    for line in raw_output.splitlines():
        extracted = _extract_event_result(line)
        if extracted is not None:
            result_text = extracted
    if result_text is None:
        message = "Antigravity produced no result event"
        raise ProviderError(message)
    return {
        "choices": [
            {"message": {"role": "assistant", "content": result_text}},
        ],
    }


def _extract_event_result(raw_line: str) -> str | None:
    """Extract result text from a raw event line when present."""
    event = _parse_line(raw_line)
    if event is None or event.get("event") != "result":
        return None
    event_result = event.get("result")
    if not isinstance(event_result, dict):
        return None
    extracted = _extract_result_text(event_result)
    return extracted or None


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

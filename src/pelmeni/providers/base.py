"""Base LLM provider interfaces, errors, and http utilities.

Canonical OpenAI-shaped message/tool/response contract:

Messages:
    list[dict] containing OpenAI-formatted chat messages:
    - User message:
        {"role": "user", "content": str}
    - Assistant message (text only):
        {"role": "assistant", "content": str}
    - Assistant message (tool calls):
        {
            "role": "assistant",
            "content": str | None,
            "tool_calls": [
                {
                    "id": str,
                    "type": "function",
                    "function": {"name": str, "arguments": str},
                }
            ]
        }
    - Tool response message:
        {"role": "tool", "tool_call_id": str, "content": str}

Tools:
    Sequence[dict] | None (or list[dict] | None):
    OpenAI function tool specifications, e.g.:
        [
            {
                "type": "function",
                "function": {
                    "name": str,
                    "description": str,
                    "parameters": dict,
                }
            }
        ]

Response format:
    dict normalized to OpenAI response structure:
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": str | None,
                        "tool_calls": list[dict] | None,  # optional if present
                    }
                }
            ]
        }
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Protocol

import httpx

from pelmeni.dto.credentials import (
    ApiKeyCredentials,
    NoCredentials,
    OAuthCredentials,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

ProviderCredentials = (
    ApiKeyCredentials | OAuthCredentials | NoCredentials | None
)


class ProviderError(Exception):
    """LLM provider request failed."""


class Provider(Protocol):
    """Protocol for LLM provider adapters."""

    def chat(
        self,
        messages: list[dict],
        tools: Sequence[dict] | None,
        model: str,
        credentials: ProviderCredentials,
    ) -> dict:
        """Send chat completion request to LLM provider."""


_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 300.0
_WRITE_TIMEOUT = 30.0
_POOL_TIMEOUT = 10.0

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=_CONNECT_TIMEOUT,
    read=_READ_TIMEOUT,
    write=_WRITE_TIMEOUT,
    pool=_POOL_TIMEOUT,
)


@contextlib.contextmanager
def handle_http_errors(provider_name: str) -> Generator[None]:
    """Normalize httpx and JSON decode errors to ProviderError."""
    try:
        yield
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = f"{provider_name} request failed with status {status}"
        raise ProviderError(msg) from exc
    except (httpx.HTTPError, ValueError) as exc:
        msg = f"{provider_name} request failed: {type(exc).__name__}"
        raise ProviderError(msg) from exc

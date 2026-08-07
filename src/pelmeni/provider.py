"""Provider client: raw HTTP to an OpenAI-compatible /chat/completions endpoint.

Step-1 scope: one hardcoded provider (LM Studio local server). The provider
layer with config.toml routing arrives in build step 2 — this module is
shaped so it becomes a thin wrapper then, not a rewrite.
"""

import httpx

# Chebupelka-style constants; moved to config/credentials in step 2.
API_KEY = "lm-studio"  # LM Studio ignores the key but the header is required
BASE_URL = "http://localhost:1234/v1"
MODEL = "qwen/qwen3-8b"

_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 300.0
_WRITE_TIMEOUT = 30.0
_POOL_TIMEOUT = 10.0
_TIMEOUT = httpx.Timeout(
    connect=_CONNECT_TIMEOUT,
    read=_READ_TIMEOUT,
    write=_WRITE_TIMEOUT,
    pool=_POOL_TIMEOUT,
)


class ProviderError(Exception):
    """LLM provider request failed."""


def _send(payload: dict) -> dict:
    """POST chat payload, raise on HTTP errors, return parsed JSON."""
    resp = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """One round-trip to the chat API. Returns the raw response JSON."""
    payload: dict = {"model": MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
    try:
        return _send(payload)
    except (httpx.HTTPError, ValueError) as exc:
        msg = f"Provider request failed: {exc}"
        raise ProviderError(msg) from exc

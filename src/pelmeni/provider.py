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

_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """One round-trip to the chat API. Returns the raw response JSON."""
    payload: dict = {"model": MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
    resp = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()

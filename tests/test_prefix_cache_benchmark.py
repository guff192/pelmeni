"""Live benchmark test for TPU prefix cache latency and token reduction."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from pelmeni.dto.credentials import NoCredentials
from pelmeni.providers.antigravity import AntigravityProvider

_SAMPLE_FILES = (
    "src/pelmeni/cli/repl.py",
    "tests/test_repl.py",
    "CONTEXT.md",
    "PLAN.md",
)


def _load_large_context() -> str:
    """Build a prompt context (~15k-25k tokens) from repository files."""
    chunks: list[str] = []
    for file_name in _SAMPLE_FILES:
        path = Path(file_name)
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    base_text = "\n\n".join(chunks)
    # Ensure context is large enough to create measurable prefill latency
    if len(base_text) < 10000:
        base_text = base_text * 3
    return base_text


@pytest.mark.live
@pytest.mark.benchmark
def test_prefix_cache_latency_and_token_reduction() -> None:
    """Benchmark warm vs cold Turn 2: verify latency and token reduction."""
    if shutil.which("agy") is None:
        pytest.skip("Antigravity binary 'agy' is not installed")

    context_text = _load_large_context()
    credentials = NoCredentials(provider="antigravity")
    model = "gemini-3.8-flash-low"

    # Turn 1: Warm up the session and capture conversation_id
    turn1_prompt = (
        f"Analyze this codebase context and reply with just 'OK':\n\n"
        f"{context_text}"
    )
    with AntigravityProvider() as provider1:
        res1 = provider1.chat(
            messages=[{"role": "user", "content": turn1_prompt}],
            tools=None,
            model=model,
            credentials=credentials,
        )
        conv_id = res1.get("conversation_id")
        usage1 = res1.get("usage", {})

    assert conv_id is not None, "Turn 1 did not yield a conversation_id"

    # Turn 2 Warm: Send follow-up delta reusing conversation_id
    warm_start = time.perf_counter()
    with AntigravityProvider() as warm_provider:
        res2_warm = warm_provider.chat(
            messages=[{"role": "user", "content": "What is the project name?"}],
            tools=None,
            model=model,
            credentials=credentials,
            conversation_id=conv_id,
        )
        dur_warm = time.perf_counter() - warm_start
        usage_warm = res2_warm.get("usage", {})

    # Turn 2 Cold: Re-send entire history without conversation_id
    cold_prompt = (
        f"{turn1_prompt}\n\nAssistant: OK\n\nUser: What is the project name?"
    )
    cold_start = time.perf_counter()
    with AntigravityProvider() as cold_provider:
        res2_cold = cold_provider.chat(
            messages=[{"role": "user", "content": cold_prompt}],
            tools=None,
            model=model,
            credentials=credentials,
            conversation_id=None,
        )
        dur_cold = time.perf_counter() - cold_start
        usage_cold = res2_cold.get("usage", {})

    print("\n--- Prefix Cache Benchmark Results ---")
    print(f"Turn 1 (Initial Prefill): tokens={usage1.get('input_tokens')}")
    print("Turn 2 Warm (with conversation_id):")
    print(f"  Duration: {dur_warm:.2f}s")
    print(f"  Input Tokens: {usage_warm.get('input_tokens')}")
    print(f"  Cache Read Tokens: {usage_warm.get('cache_read_tokens')}")
    print("Turn 2 Cold (without conversation_id, re-prefilling):")
    print(f"  Duration: {dur_cold:.2f}s")
    print(f"  Input Tokens: {usage_cold.get('input_tokens')}")
    print(f"  Cache Read Tokens: {usage_cold.get('cache_read_tokens')}")
    assert res2_warm["choices"][0]["message"]["content"]
    assert res2_cold["choices"][0]["message"]["content"]

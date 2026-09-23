"""Tests for the unified bus factory with Redis fallback."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from pelmeni.bus.factory import create_bus
from pelmeni.bus.in_memory import InMemoryBus
from pelmeni.bus.redis_bus import RedisBus


def test_create_bus_memory_url() -> None:
    """Explicit memory:// URL returns an InMemoryBus instance."""

    async def _run() -> None:
        bus = await create_bus(url="memory://")
        assert isinstance(bus, InMemoryBus)

    asyncio.run(_run())


def test_create_bus_force_in_memory() -> None:
    """force_in_memory flag returns InMemoryBus without network checks."""

    async def _run() -> None:
        bus = await create_bus(
            url="redis://127.0.0.1:6379/0",
            force_in_memory=True,
        )
        assert isinstance(bus, InMemoryBus)

    asyncio.run(_run())


def test_create_bus_fallback_when_redis_unavailable() -> None:
    """Unavailable Redis endpoint falls back smoothly to InMemoryBus."""

    async def _run() -> None:
        # Non-routable / unused local port with very fast timeout
        bus = await create_bus(
            url="redis://127.0.0.1:59998/0",
            timeout=0.05,
        )
        assert isinstance(bus, InMemoryBus)

    asyncio.run(_run())


def test_create_bus_returns_redis_when_connected() -> None:
    """Reachable Redis endpoint returns a RedisBus instance."""

    async def _run() -> None:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch(
            "pelmeni.bus.factory.aioredis.from_url", return_value=mock_client
        ):
            bus = await create_bus(
                url="redis://localhost:6379/0",
                timeout=0.5,
            )
            assert isinstance(bus, RedisBus)

    asyncio.run(_run())

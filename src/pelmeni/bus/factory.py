"""Unified bus factory with Redis auto-detection and InMemory fallback."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from redis import asyncio as aioredis
from redis.exceptions import RedisError

from pelmeni.bus.in_memory import InMemoryBus
from pelmeni.bus.redis_bus import RedisBus

if TYPE_CHECKING:
    from pelmeni.bus.protocol import BusProtocol

_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


async def create_bus(
    url: str | None = None,
    *,
    force_in_memory: bool = False,
    timeout: float = 0.5,  # noqa: ASYNC109
) -> BusProtocol:
    """Create bus instance detecting Redis availability with InMemory fallback.

    Returns a RedisBus if Redis is reachable, or InMemoryBus otherwise.
    """
    if force_in_memory:
        return InMemoryBus(url=url)

    if url and url.startswith(("memory://", "inmemory://")):
        return InMemoryBus(url=url)

    target_url = url or _DEFAULT_REDIS_URL
    is_available = await _probe_redis(target_url, timeout=timeout)
    if is_available:
        return RedisBus(url=target_url)

    return InMemoryBus(url=target_url)


async def _probe_redis(
    url: str,
    *,
    timeout: float,  # noqa: ASYNC109
) -> bool:
    """Probe Redis instance with ping, returning True if reachable."""
    client = aioredis.from_url(url, socket_connect_timeout=timeout)
    is_reachable = False
    try:
        is_reachable = bool(
            await asyncio.wait_for(client.ping(), timeout=timeout),
        )
    except RedisError, OSError, TimeoutError:
        is_reachable = False
    with contextlib.suppress(Exception):
        await client.aclose()
    return is_reachable

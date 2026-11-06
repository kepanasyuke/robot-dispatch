from __future__ import annotations

import asyncio
import uuid

import redis.asyncio as redis

from robot_dispatch.logging_setup import get_logger

logger = get_logger("lock")

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_EXTEND = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""


class RedisLock:
    """Best-effort leader election for the dispatcher loop.

    Correctness does not depend on this lock: `FOR UPDATE SKIP LOCKED` already
    guarantees a task is handed out once. The lock only keeps several replicas
    from spinning on the same empty queue, and it degrades to "no lock" when
    Redis is unreachable.
    """

    def __init__(self, url: str, key: str = "robot-dispatch:dispatcher:leader", ttl_ms: int = 10_000) -> None:
        self._url = url
        self._key = key
        self._ttl_ms = ttl_ms
        self._client: redis.Redis | None = None
        self._token = uuid.uuid4().hex
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def connect(self) -> None:
        try:
            self._client = redis.from_url(self._url, decode_responses=True)
            await self._client.ping()
            self._available = True
        except Exception as exc:  # noqa: BLE001 - optional dependency
            logger.warning("redis unavailable, running without leader lock", error=str(exc))
            self._available = False
            self._client = None

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def acquire(self) -> bool:
        if self._client is None:
            return True
        try:
            return bool(
                await self._client.set(self._key, self._token, nx=True, px=self._ttl_ms)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis lock acquire failed", error=str(exc))
            return True

    async def extend(self) -> bool:
        if self._client is None:
            return True
        try:
            return bool(await self._client.eval(_EXTEND, 1, self._key, self._token, self._ttl_ms))
        except Exception:  # noqa: BLE001
            return True

    async def release(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.eval(_RELEASE, 1, self._key, self._token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis lock release failed", error=str(exc))


class NullLock:
    """Used when Redis is disabled entirely."""

    available = False

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def acquire(self) -> bool:
        return True

    async def extend(self) -> bool:
        return True

    async def release(self) -> None:
        return None


async def sleep_ms(milliseconds: float) -> None:
    await asyncio.sleep(max(milliseconds, 0) / 1000)

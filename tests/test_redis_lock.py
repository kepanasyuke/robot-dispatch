from __future__ import annotations

import pytest

from robot_dispatch.infra import redis_lock as lock_module
from robot_dispatch.infra.redis_lock import NullLock, RedisLock, sleep_ms


class FakeRedis:
    def __init__(self, *, ping_error: Exception | None = None, set_result=True, eval_result=1) -> None:
        self.ping_error = ping_error
        self.set_result = set_result
        self.eval_result = eval_result
        self.set_calls: list[tuple] = []
        self.eval_calls: list[tuple] = []
        self.closed = False
        self.set_error: Exception | None = None
        self.eval_error: Exception | None = None

    async def ping(self) -> bool:
        if self.ping_error:
            raise self.ping_error
        return True

    async def set(self, key, token, nx: bool = False, px: int | None = None):
        if self.set_error:
            raise self.set_error
        self.set_calls.append((key, token, nx, px))
        return self.set_result

    async def eval(self, script, numkeys, key, *args):
        if self.eval_error:
            raise self.eval_error
        self.eval_calls.append((script, numkeys, key, args))
        return self.eval_result

    async def aclose(self) -> None:
        self.closed = True


def patch_redis(monkeypatch, client: FakeRedis) -> None:
    def from_url(url: str, decode_responses: bool = True) -> FakeRedis:
        return client

    monkeypatch.setattr(lock_module.redis, "from_url", from_url)


async def test_connect_marks_available(monkeypatch) -> None:
    client = FakeRedis()
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")

    await lock.connect()

    assert lock.available is True


async def test_connect_degrades_without_redis(monkeypatch) -> None:
    client = FakeRedis(ping_error=OSError("no redis"))
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")

    await lock.connect()

    assert lock.available is False
    assert await lock.acquire() is True


async def test_acquire_uses_set_nx(monkeypatch) -> None:
    client = FakeRedis()
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test", key="leader", ttl_ms=5000)
    await lock.connect()

    assert await lock.acquire() is True
    key, _token, nx, px = client.set_calls[0]
    assert (key, nx, px) == ("leader", True, 5000)


async def test_acquire_reports_loss(monkeypatch) -> None:
    client = FakeRedis(set_result=False)
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")
    await lock.connect()

    assert await lock.acquire() is False


async def test_acquire_failure_degrades_to_true(monkeypatch) -> None:
    client = FakeRedis()
    client.set_error = OSError("connection lost")
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")
    await lock.connect()

    assert await lock.acquire() is True


async def test_extend_and_release(monkeypatch) -> None:
    client = FakeRedis()
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")
    await lock.connect()

    assert await lock.extend() is True
    await lock.release()

    assert len(client.eval_calls) == 2
    assert client.eval_calls[0][2] == "robot-dispatch:dispatcher:leader"


async def test_extend_failure_degrades_to_true(monkeypatch) -> None:
    client = FakeRedis()
    client.eval_error = OSError("lost")
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")
    await lock.connect()

    assert await lock.extend() is True
    await lock.release()


async def test_close_releases_client(monkeypatch) -> None:
    client = FakeRedis()
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test")
    await lock.connect()

    await lock.close()

    assert client.closed is True
    assert await lock.acquire() is True


async def test_unconnected_lock_is_permissive() -> None:
    lock = RedisLock("redis://test")

    assert await lock.acquire() is True
    assert await lock.extend() is True
    await lock.release()
    await lock.close()


async def test_null_lock_contract() -> None:
    lock = NullLock()

    assert lock.available is False
    await lock.connect()
    assert await lock.acquire() is True
    assert await lock.extend() is True
    await lock.release()
    await lock.close()


async def test_sleep_ms_handles_negative() -> None:
    await sleep_ms(-10)
    await sleep_ms(0)


@pytest.mark.parametrize("ttl", [1000, 5000, 10_000])
async def test_ttl_is_passed_to_redis(monkeypatch, ttl) -> None:
    client = FakeRedis()
    patch_redis(monkeypatch, client)
    lock = RedisLock("redis://test", ttl_ms=ttl)
    await lock.connect()

    await lock.acquire()

    assert client.set_calls[0][3] == ttl

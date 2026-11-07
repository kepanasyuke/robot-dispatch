from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from robot_dispatch.workers import consumer_worker, dispatcher_worker


class FakeBroker:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


class FakeConsumer:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.started = 0

    async def start(self) -> None:
        self.started += 1


_REAL_EVENT = asyncio.Event


def preset_event() -> asyncio.Event:
    event = _REAL_EVENT()
    event.set()
    return event


def make_runtime(settings, broker):
    @asynccontextmanager
    async def fake_runtime(_settings):
        yield SimpleNamespace(settings=settings, uow_factory=lambda: None, broker=broker)

    return fake_runtime


async def test_consumer_worker_runs_until_stop(monkeypatch, settings) -> None:
    broker = FakeBroker()
    created: list[FakeConsumer] = []

    def factory(*args, **kwargs):
        consumer = FakeConsumer(*args, **kwargs)
        created.append(consumer)
        return consumer

    monkeypatch.setattr(consumer_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(consumer_worker, "runtime", make_runtime(settings, broker))
    monkeypatch.setattr(consumer_worker, "RobotEventConsumer", factory)
    monkeypatch.setattr(consumer_worker.asyncio, "Event", preset_event)

    await consumer_worker.main()

    assert created and created[0].started == 1
    assert broker.closed == 1


async def test_consumer_worker_cli_delegates_to_run(monkeypatch) -> None:
    called: list[str] = []

    def fake_run(factory) -> None:
        called.append(factory.__name__)

    monkeypatch.setattr(consumer_worker, "run", fake_run)

    consumer_worker.cli()

    assert called == ["main"]


async def test_dispatcher_worker_runs_loops(monkeypatch, settings) -> None:
    broker = FakeBroker()
    dispatched: list[int] = []

    class FakeDispatcher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def dispatch_once(self):
            dispatched.append(1)
            return SimpleNamespace(dispatched=False)

    monkeypatch.setattr(dispatcher_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(dispatcher_worker, "runtime", make_runtime(settings, broker))
    monkeypatch.setattr(dispatcher_worker, "DispatcherService", FakeDispatcher)
    monkeypatch.setattr(dispatcher_worker.asyncio, "Event", preset_event)

    await asyncio.wait_for(dispatcher_worker.main(), timeout=5)

    assert dispatched == []


async def test_dispatcher_worker_uses_null_lock_without_redis(monkeypatch, settings) -> None:
    broker = FakeBroker()
    locks: list[object] = []

    class SpyNullLock:
        available = False

        def __init__(self) -> None:
            locks.append(self)

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

    monkeypatch.setattr(dispatcher_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(dispatcher_worker, "runtime", make_runtime(settings, broker))
    monkeypatch.setattr(dispatcher_worker, "NullLock", SpyNullLock)
    monkeypatch.setattr(dispatcher_worker.asyncio, "Event", preset_event)

    await asyncio.wait_for(dispatcher_worker.main(), timeout=5)

    assert len(locks) == 1


async def test_dispatcher_worker_connects_redis_when_configured(monkeypatch, settings) -> None:
    broker = FakeBroker()
    events: list[str] = []

    class SpyRedisLock:
        available = True

        def __init__(self, url: str, ttl_ms: int = 10_000) -> None:
            self.url = url
            self.ttl_ms = ttl_ms

        async def connect(self) -> None:
            events.append("connect")

        async def close(self) -> None:
            events.append("close")

        async def acquire(self) -> bool:
            return True

        async def extend(self) -> bool:
            return True

        async def release(self) -> None:
            events.append("release")

    redis_settings = settings.model_copy(update={"redis_url": "redis://localhost:6379/0"})
    monkeypatch.setattr(dispatcher_worker, "get_settings", lambda: redis_settings)
    monkeypatch.setattr(dispatcher_worker, "runtime", make_runtime(redis_settings, broker))
    monkeypatch.setattr(dispatcher_worker, "RedisLock", SpyRedisLock)
    monkeypatch.setattr(dispatcher_worker.asyncio, "Event", preset_event)

    await asyncio.wait_for(dispatcher_worker.main(), timeout=5)

    assert events[0] == "connect"
    assert events[-1] == "close"


async def test_dispatcher_worker_cli_delegates_to_run(monkeypatch) -> None:
    called: list[str] = []

    def fake_run(factory) -> None:
        called.append(factory.__name__)

    monkeypatch.setattr(dispatcher_worker, "run", fake_run)

    dispatcher_worker.cli()

    assert called == ["main"]


@pytest.mark.parametrize("module", [consumer_worker, dispatcher_worker])
def test_workers_expose_cli(module) -> None:
    assert callable(module.cli)
    assert callable(module.main)


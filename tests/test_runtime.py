from __future__ import annotations

import asyncio

import pytest

from robot_dispatch.db.base import Base
from robot_dispatch.db.models import Robot
from robot_dispatch.domain.enums import RobotStatus
from robot_dispatch.workers import runtime as runtime_module
from robot_dispatch.workers.dispatcher_worker import LeadershipGate
from robot_dispatch.workers.runtime import install_signal_handlers, periodic, run, runtime


class FakeLock:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.acquired = 0
        self.extended = 0
        self.released = 0
        self.acquire_result = True
        self.extend_result = True

    async def acquire(self) -> bool:
        self.acquired += 1
        return self.acquire_result

    async def extend(self) -> bool:
        self.extended += 1
        return self.extend_result

    async def release(self) -> None:
        self.released += 1

    async def close(self) -> None:
        return None


class FakeBroker:
    def __init__(self) -> None:
        self.queues: list[object] = []
        self.closed = False

    async def connect(self) -> None:
        return None

    async def ensure_robot_queue(self, robot_id) -> None:
        self.queues.append(robot_id)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def runtime_settings(tmp_path, settings):
    return settings.model_copy(update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}"})


async def prepare_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def test_runtime_yields_components(runtime_settings, monkeypatch) -> None:
    broker = FakeBroker()
    monkeypatch.setattr(runtime_module, "Broker", lambda *args, **kwargs: broker)

    async with runtime(runtime_settings) as rt:
        assert rt.settings is runtime_settings
        assert rt.broker is broker
        assert rt.engine is not None

    assert broker.closed is True


async def test_runtime_ensures_robot_queues(runtime_settings, monkeypatch) -> None:
    broker = FakeBroker()
    monkeypatch.setattr(runtime_module, "Broker", lambda *args, **kwargs: broker)

    engine = runtime_module.create_engine(runtime_settings.database_url)
    await prepare_schema(engine)
    async with runtime_module.create_session_factory(engine)() as session:
        session.add(
            Robot.new(
                name="robot-1",
                namespace="/r1",
                capabilities=["delivery"],
                status=RobotStatus.IDLE,
            )
        )
        await session.commit()
    await engine.dispose()

    async with runtime(runtime_settings) as rt:
        assert rt.broker is broker

    assert len(broker.queues) == 1


async def test_runtime_survives_missing_schema(runtime_settings, monkeypatch) -> None:
    broker = FakeBroker()
    monkeypatch.setattr(runtime_module, "Broker", lambda *args, **kwargs: broker)

    async with runtime(runtime_settings) as rt:
        assert rt.broker is broker

    assert broker.queues == []


async def test_periodic_stops_on_event() -> None:
    stop = asyncio.Event()
    calls = 0

    async def step() -> None:
        nonlocal calls
        calls += 1
        stop.set()

    await asyncio.wait_for(periodic("test", step, 1, stop), timeout=2)

    assert calls == 1


async def test_periodic_survives_failures() -> None:
    stop = asyncio.Event()
    calls = 0

    async def step() -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            stop.set()
        raise RuntimeError("iteration failed")

    await asyncio.wait_for(periodic("test", step, 1, stop), timeout=2)

    assert calls == 2


async def test_periodic_propagates_cancellation() -> None:
    stop = asyncio.Event()

    async def step() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await periodic("test", step, 1, stop)


def test_install_signal_handlers_is_safe_on_windows() -> None:
    stop = asyncio.Event()

    async def main() -> None:
        install_signal_handlers(stop)

    asyncio.run(main())


def test_run_executes_coroutine() -> None:
    executed: list[str] = []

    async def main() -> None:
        executed.append("done")

    run(main)

    assert executed == ["done"]


def test_leadership_gate_is_leader_without_lock() -> None:
    gate = LeadershipGate(FakeLock(available=False))

    assert gate.is_leader is True


async def test_leadership_gate_acquires_and_releases() -> None:
    lock = FakeLock()
    gate = LeadershipGate(lock, ttl_ms=1)
    stop = asyncio.Event()

    task = asyncio.create_task(gate.maintain(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)

    assert lock.acquired >= 1
    assert lock.released == 1


async def test_leadership_gate_extends_existing_lease() -> None:
    lock = FakeLock()
    gate = LeadershipGate(lock, ttl_ms=1)
    stop = asyncio.Event()

    task = asyncio.create_task(gate.maintain(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)

    assert lock.acquired >= 1
    assert lock.extended >= 1
    assert lock.released == 1


async def test_leadership_gate_skips_release_when_not_leader() -> None:
    lock = FakeLock()
    lock.acquire_result = False
    gate = LeadershipGate(lock, ttl_ms=1)
    stop = asyncio.Event()
    stop.set()

    await gate.maintain(stop)

    assert lock.released == 0



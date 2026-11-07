from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from robot_dispatch.db.base import Base
from robot_dispatch.db.models import OutboxMessage, Robot, Task, TaskEvent
from robot_dispatch.db.session import create_engine, create_session_factory
from robot_dispatch.db.uow import SqlUnitOfWork, make_sql_uow_factory
from robot_dispatch.domain.enums import RobotStatus

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory(tmp_path) -> async_sessionmaker:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.fixture
def uow_factory(session_factory):
    return make_sql_uow_factory(session_factory)


async def add_task(uow, **kwargs) -> Task:
    kwargs.setdefault("available_at", NOW)
    task = Task.new(task_type=kwargs.pop("task_type", "delivery"), **kwargs)
    await uow.tasks.add(task)
    return task


def make_robot(
    name: str = "robot-1",
    *,
    status: RobotStatus = RobotStatus.IDLE,
    seen: datetime | None = NOW,
) -> Robot:
    return Robot.new(
        name=name,
        namespace=f"/{name}",
        capabilities=["delivery"],
        status=status,
        last_seen_at=seen,
    )


async def test_uow_commits_and_reads_back(uow_factory) -> None:
    async with uow_factory() as uow:
        task = await add_task(uow)
        await uow.commit()
        task_id = task.id

    async with uow_factory() as uow:
        loaded = await uow.tasks.get(task_id)
        assert loaded is not None
        assert loaded.status == "pending"


async def test_uow_rolls_back_without_commit(uow_factory) -> None:
    async with uow_factory() as uow:
        task = await add_task(uow, external_id="rolled-back")
        task_id = task.id

    async with uow_factory() as uow:
        assert await uow.tasks.get(task_id) is None
        assert await uow.tasks.get_by_external_id("rolled-back") is None


async def test_uow_rolls_back_on_exception(uow_factory) -> None:
    with pytest.raises(RuntimeError):
        async with uow_factory() as uow:
            task = await add_task(uow, external_id="boom")
            task_id = task.id
            await uow.commit()
            raise RuntimeError("stop")

    async with uow_factory() as uow:
        assert await uow.tasks.get(task_id) is not None


async def test_uow_commit_requires_session(uow_factory) -> None:
    uow = uow_factory()
    with pytest.raises(RuntimeError):
        await uow.commit()


async def test_uow_rollback_and_flush_are_safe_without_session(uow_factory) -> None:
    uow = uow_factory()
    await uow.rollback()
    await uow.flush()
    assert uow.session is None


async def test_explicit_rollback_forgets_changes(uow_factory) -> None:
    async with uow_factory() as uow:
        task = await add_task(uow, external_id="explicit")
        await uow.flush()
        await uow.rollback()
        task_id = task.id

    async with uow_factory() as uow:
        assert await uow.tasks.get(task_id) is None


async def test_external_id_lookup(uow_factory) -> None:
    async with uow_factory() as uow:
        await add_task(uow, external_id="order-42")
        await uow.commit()

    async with uow_factory() as uow:
        found = await uow.tasks.get_by_external_id("order-42")
        assert found is not None
        assert found.external_id == "order-42"
        assert await uow.tasks.get_by_external_id("missing") is None


async def test_lock_ready_orders_by_priority(uow_factory) -> None:
    async with uow_factory() as uow:
        await add_task(uow, priority=10, external_id="low")
        await add_task(uow, priority=900, external_id="high")
        await add_task(uow, priority=100, external_id="mid")
        await uow.commit()

    async with uow_factory() as uow:
        ready = await uow.tasks.lock_ready(now=NOW, limit=10)
        assert [task.priority for task in ready] == [900, 100, 10]


async def test_lock_ready_skips_future_tasks(uow_factory) -> None:
    async with uow_factory() as uow:
        await add_task(uow, available_at=NOW + timedelta(minutes=5), external_id="later")
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.tasks.lock_ready(now=NOW, limit=10) == []


async def test_lock_ready_respects_limit(uow_factory) -> None:
    async with uow_factory() as uow:
        for index in range(5):
            await add_task(uow, external_id=f"task-{index}")
        await uow.commit()

    async with uow_factory() as uow:
        assert len(await uow.tasks.lock_ready(now=NOW, limit=2)) == 2


async def test_lock_expired_leases_finds_only_expired(uow_factory) -> None:
    async with uow_factory() as uow:
        expired = await add_task(uow, external_id="expired")
        expired.status = "running"
        expired.lease_expires_at = NOW - timedelta(seconds=1)
        fresh = await add_task(uow, external_id="fresh")
        fresh.status = "running"
        fresh.lease_expires_at = NOW + timedelta(seconds=60)
        pending = await add_task(uow, external_id="pending")
        await uow.commit()
        expired_id = expired.id
        assert pending.lease_expires_at is None

    async with uow_factory() as uow:
        leases = await uow.tasks.lock_expired_leases(now=NOW, limit=10)
        assert [task.id for task in leases] == [expired_id]


async def test_list_filters_and_paginates(uow_factory) -> None:
    async with uow_factory() as uow:
        first = await add_task(uow, external_id="a")
        first.status = "failed"
        second = await add_task(uow, task_type="patrol", external_id="b")
        assert second.type == "patrol"
        await uow.commit()

    async with uow_factory() as uow:
        assert len(await uow.tasks.list()) == 2
        assert [task.external_id for task in await uow.tasks.list(statuses=["failed"])] == ["a"]
        assert [task.external_id for task in await uow.tasks.list(task_type="patrol")] == ["b"]
        assert await uow.tasks.list(statuses=["succeeded"]) == []
        page = await uow.tasks.list(limit=1, offset=0)
        assert len(page) == 1
        assert len(await uow.tasks.list(limit=1, offset=1)) == 1


async def test_list_filters_by_robot(uow_factory) -> None:
    async with uow_factory() as uow:
        robot = make_robot()
        await uow.robots.add(robot)
        task = await add_task(uow, external_id="with-robot")
        task.robot_id = robot.id
        await add_task(uow, external_id="without-robot")
        await uow.commit()
        robot_id = robot.id

    async with uow_factory() as uow:
        filtered = await uow.tasks.list(robot_id=robot_id)
        assert [task.external_id for task in filtered] == ["with-robot"]


async def test_count_by_status(uow_factory) -> None:
    async with uow_factory() as uow:
        await add_task(uow, external_id="1")
        await add_task(uow, external_id="2")
        third = await add_task(uow, external_id="3")
        third.status = "failed"
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.tasks.count_by_status() == {"pending": 2, "failed": 1}


async def test_robot_repository(uow_factory) -> None:
    async with uow_factory() as uow:
        robot = make_robot("robot-1")
        await uow.robots.add(robot)
        await uow.commit()
        robot_id = robot.id

    async with uow_factory() as uow:
        loaded = await uow.robots.get(robot_id)
        assert loaded is not None
        assert loaded.capability_names == ["delivery"]
        assert (await uow.robots.get_by_name("robot-1")) is not None
        assert await uow.robots.get_by_name("robot-x") is None
        assert [item.name for item in await uow.robots.list()] == ["robot-1"]


async def test_find_idle_for_requires_live_robot(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.robots.add(make_robot("stale", seen=NOW - timedelta(seconds=600)))
        await uow.robots.add(make_robot("busy", status=RobotStatus.BUSY))
        fresh = make_robot("fresh")
        await uow.robots.add(fresh)
        await uow.commit()
        fresh_id = fresh.id

    async with uow_factory() as uow:
        found = await uow.robots.find_idle_for(task_type="delivery", now=NOW, offline_after=60)
        assert found is not None
        assert found.id == fresh_id


async def test_find_idle_for_returns_none_without_candidates(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.robots.add(make_robot("stale", seen=NOW - timedelta(seconds=600)))
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.robots.find_idle_for(task_type="delivery", now=NOW, offline_after=60) is None


async def test_event_repository_orders_events(uow_factory) -> None:
    async with uow_factory() as uow:
        task = await add_task(uow, external_id="events")
        await uow.events.add(TaskEvent.new(task_id=task.id, kind="created", to_status="pending"))
        await uow.events.add(
            TaskEvent.new(task_id=task.id, kind="assigned", from_status="pending", to_status="assigned")
        )
        await uow.commit()
        task_id = task.id

    async with uow_factory() as uow:
        events = await uow.events.list_for_task(task_id)
        assert [event.kind for event in events] == ["created", "assigned"]
        assert await uow.events.list_for_task(uuid.uuid4()) == []


async def test_outbox_lifecycle(uow_factory) -> None:
    async with uow_factory() as uow:
        message = OutboxMessage.new(
            exchange="robot.commands",
            routing_key="command.1",
            payload={"task_id": "1"},
            message_id="m-1",
        )
        message.available_at = NOW
        await uow.outbox.add(message)
        await uow.commit()
        message_id = message.id

    async with uow_factory() as uow:
        pending = await uow.outbox.lock_pending(now=NOW, limit=10)
        assert [item.message_id for item in pending] == ["m-1"]
        target = pending[0]
        await uow.outbox.mark_sent(target, NOW)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.outbox.lock_pending(now=NOW, limit=10) == []
        sent = await uow.session.get(OutboxMessage, message_id)
        assert sent is not None
        assert sent.attempts == 1
        assert sent.sent_at is not None


async def test_outbox_marks_failed_with_error_truncation(uow_factory) -> None:
    async with uow_factory() as uow:
        message = OutboxMessage.new(
            exchange="robot.commands",
            routing_key="command.1",
            payload={},
            message_id="m-2",
        )
        message.available_at = NOW
        await uow.outbox.add(message)
        await uow.commit()

    async with uow_factory() as uow:
        pending = await uow.outbox.lock_pending(now=NOW, limit=10)
        target = pending[0]
        await uow.outbox.mark_failed(target, "x" * 3000, NOW + timedelta(seconds=30), attempts=2)
        await uow.commit()
        assert target.attempts == 2
        assert target.last_error is not None
        assert len(target.last_error) == 2000


async def test_outbox_respects_available_at(uow_factory) -> None:
    async with uow_factory() as uow:
        message = OutboxMessage.new(
            exchange="robot.commands",
            routing_key="command.1",
            payload={},
            message_id="m-3",
        )
        message.available_at = NOW + timedelta(minutes=10)
        await uow.outbox.add(message)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.outbox.lock_pending(now=NOW, limit=10) == []


async def test_sql_uow_exposes_repositories(uow_factory) -> None:
    async with uow_factory() as uow:
        assert isinstance(uow, SqlUnitOfWork)
        assert uow.session is not None
        assert hasattr(uow, "tasks")
        assert hasattr(uow, "robots")
        assert hasattr(uow, "events")
        assert hasattr(uow, "outbox")

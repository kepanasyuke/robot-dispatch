from __future__ import annotations

from datetime import timedelta

from robot_dispatch.domain.enums import RobotStatus, TaskStatus
from robot_dispatch.messaging.messages import COMMANDS_EXCHANGE
from robot_dispatch.services.dispatcher import DispatcherService, LeaseReaper
from robot_dispatch.services.task_service import CreateTaskCommand, TaskService


async def seed_task(service: TaskService, **kwargs):
    command = CreateTaskCommand(type=kwargs.pop("type", "delivery"), payload={}, **kwargs)
    return (await service.create(command)).task


async def test_dispatch_assigns_idle_robot(uow_factory, settings, clock, robot) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await seed_task(tasks)
    dispatcher = DispatcherService(uow_factory, settings, clock=clock)

    outcome = await dispatcher.dispatch_once()

    assert outcome.dispatched is True
    assert outcome.task_id == created.id
    assert outcome.robot_id == robot.id
    assert outcome.attempt == 1

    async with uow_factory() as uow:
        task = await uow.tasks.get(created.id)
        stored_robot = await uow.robots.get(robot.id)
        outbox = list(uow._store.outbox)

    assert task.status == TaskStatus.ASSIGNED.value
    assert task.robot_id == robot.id
    assert task.attempts == 1
    assert task.command_id is not None
    assert task.lease_expires_at == clock.moment + timedelta(seconds=task.timeout_seconds)
    assert stored_robot.status == RobotStatus.BUSY.value
    assert stored_robot.current_task_id == task.id

    assert len(outbox) == 1
    message = outbox[0]
    assert message.exchange == COMMANDS_EXCHANGE
    assert message.routing_key == f"command.{robot.id}"
    assert message.message_id == str(task.command_id)
    assert message.expiration_ms == task.timeout_seconds * 1000
    assert message.payload["task_id"] == str(task.id)
    assert message.payload["attempt"] == 1


async def test_dispatch_without_idle_robots_keeps_task_pending(uow_factory, settings, clock) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await seed_task(tasks)
    dispatcher = DispatcherService(uow_factory, settings, clock=clock)

    outcome = await dispatcher.dispatch_once()

    assert outcome.dispatched is False
    assert outcome.reason == "no_idle_robot"
    async with uow_factory() as uow:
        task = await uow.tasks.get(created.id)
    assert task.status == TaskStatus.PENDING.value
    assert task.attempts == 0


async def test_robot_capabilities_are_respected(uow_factory, settings, clock) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    from robot_dispatch.services.task_service import RobotService

    await RobotService(uow_factory, clock=clock).register(
        name="patrol-bot", namespace="/p1", capabilities=["patrol"]
    )
    delivery = await seed_task(tasks, type="delivery")
    dispatcher = DispatcherService(uow_factory, settings, clock=clock)

    outcome = await dispatcher.dispatch_once()

    assert outcome.dispatched is False
    async with uow_factory() as uow:
        task = await uow.tasks.get(delivery.id)
    assert task.status == TaskStatus.PENDING.value


async def test_priority_ordering(uow_factory, settings, clock, robot) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    low = await seed_task(tasks, priority=1)
    high = await seed_task(tasks, priority=500)
    dispatcher = DispatcherService(uow_factory, settings, clock=clock)

    first = await dispatcher.dispatch_once()
    second = await dispatcher.dispatch_once()

    assert first.task_id == high.id
    assert second.dispatched is False  # robot is busy now
    async with uow_factory() as uow:
        low_task = await uow.tasks.get(low.id)
    assert low_task.status == TaskStatus.PENDING.value


async def test_retrying_task_is_not_dispatched_before_backoff(uow_factory, settings, clock, robot) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await seed_task(tasks)
    async with uow_factory() as uow:
        task = await uow.tasks.get(created.id)
        task.status = TaskStatus.RETRYING.value
        task.available_at = clock.moment + timedelta(seconds=10)
        await uow.commit()

    dispatcher = DispatcherService(uow_factory, settings, clock=clock)
    assert (await dispatcher.dispatch_once()).dispatched is False
    assert (await dispatcher.dispatch_once()).reason == "no_ready_tasks"

    clock.advance(11)
    assert (await dispatcher.dispatch_once()).dispatched is True


async def test_expired_lease_requeues_task_and_releases_robot(
    uow_factory, settings, clock, robot
) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await seed_task(tasks)
    dispatcher = DispatcherService(uow_factory, settings, clock=clock)
    await dispatcher.dispatch_once()

    clock.advance(31)
    reaper = LeaseReaper(uow_factory, settings, clock=clock)
    assert await reaper.reap_once() == 1

    async with uow_factory() as uow:
        task = await uow.tasks.get(created.id)
        stored_robot = await uow.robots.get(robot.id)
        events = await uow.events.list_for_task(created.id)

    assert task.status == TaskStatus.RETRYING.value
    assert task.available_at == clock.moment + timedelta(seconds=5)
    assert task.lease_expires_at is None
    assert stored_robot.status == RobotStatus.IDLE.value
    assert stored_robot.current_task_id is None
    assert events[-1].kind == "lease_expired"


async def test_expired_lease_fails_task_after_max_attempts(uow_factory, settings, clock, robot) -> None:
    tasks = TaskService(uow_factory, settings, clock=clock)
    created = await seed_task(tasks, max_attempts=1)
    dispatcher = DispatcherService(uow_factory, settings, clock=clock)
    await dispatcher.dispatch_once()

    clock.advance(31)
    await LeaseReaper(uow_factory, settings, clock=clock).reap_once()

    async with uow_factory() as uow:
        task = await uow.tasks.get(created.id)
        events = await uow.events.list_for_task(created.id)

    assert task.status == TaskStatus.FAILED.value
    assert task.finished_at is not None
    assert events[-1].kind == "failed"

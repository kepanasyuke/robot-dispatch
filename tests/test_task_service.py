from __future__ import annotations

import pytest

from robot_dispatch.domain.enums import RobotStatus, TaskStatus
from robot_dispatch.services.errors import TaskConflict, TaskNotFound
from robot_dispatch.services.task_service import CreateTaskCommand, RobotService, TaskService


async def test_create_task_queues_it(uow_factory, settings, clock) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    result = await service.create(CreateTaskCommand(type="delivery", payload={"target": "a"}))

    assert result.replayed is False
    assert result.task.status == TaskStatus.PENDING.value
    assert result.task.attempts == 0
    assert result.task.max_attempts == settings.default_max_attempts
    assert result.task.timeout_seconds == settings.default_task_timeout_seconds

    events = await service.events(result.task.id)
    assert [event.kind for event in events] == ["created"]


async def test_task_type_is_never_trusted_from_payload(uow_factory, settings, clock) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    result = await service.create(
        CreateTaskCommand(type="patrol", payload={"zone": "north"}, priority=5)
    )
    stored = await service.get(result.task.id)

    assert stored.type == "patrol"
    assert stored.priority == 5
    assert stored.payload == {"zone": "north"}


async def test_external_id_makes_creation_idempotent(uow_factory, settings, clock) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    command = CreateTaskCommand(type="delivery", payload={}, external_id="order-42")

    first = await service.create(command)
    second = await service.create(command)

    assert first.replayed is False
    assert second.replayed is True
    assert second.task.id == first.task.id

    stored = await service.list()
    assert len(stored) == 1


async def test_cancel_pending_task_releases_robot(uow_factory, settings, clock, robot) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    created = await service.create(CreateTaskCommand(type="delivery", payload={}))

    async with uow_factory() as uow:
        stored = await uow.tasks.get(created.task.id)
        stored.status = TaskStatus.ASSIGNED.value
        stored.robot_id = robot.id
        stored_robot = await uow.robots.get(robot.id)
        stored_robot.status = RobotStatus.BUSY.value
        stored_robot.current_task_id = stored.id
        await uow.commit()

    cancelled = await service.cancel(created.task.id)

    assert cancelled.status == TaskStatus.CANCELLED.value
    assert cancelled.finished_at is not None
    async with uow_factory() as uow:
        released = await uow.robots.get(robot.id)
    assert released.status == RobotStatus.IDLE.value
    assert released.current_task_id is None


async def test_cancel_finished_task_conflicts(uow_factory, settings, clock) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    created = await service.create(CreateTaskCommand(type="delivery", payload={}))
    await service.cancel(created.task.id)

    with pytest.raises(TaskConflict):
        await service.cancel(created.task.id)


async def test_cancel_running_task_conflicts(uow_factory, settings, clock) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    created = await service.create(CreateTaskCommand(type="delivery", payload={}))
    async with uow_factory() as uow:
        stored = await uow.tasks.get(created.task.id)
        stored.status = TaskStatus.RUNNING.value
        await uow.commit()

    with pytest.raises(TaskConflict) as error:
        await service.cancel(created.task.id)
    assert "robot owns the execution" in str(error.value)


async def test_cancel_missing_task(uow_factory, settings, clock) -> None:
    service = TaskService(uow_factory, settings, clock=clock)
    with pytest.raises(TaskNotFound):
        await service.cancel(__import__("uuid").uuid4())


async def test_robot_registration_is_idempotent(uow_factory, clock) -> None:
    service = RobotService(uow_factory, clock=clock)

    robot, created = await service.register(name="robot-7", namespace="/r7", capabilities=["patrol"])
    assert created is True
    assert robot.status == RobotStatus.IDLE.value
    assert robot.capability_names == ["patrol"]

    again, created_again = await service.register(
        name="robot-7", namespace="/r7-new", capabilities=["delivery", "patrol"]
    )
    assert created_again is False
    assert again.id == robot.id
    assert again.namespace == "/r7-new"
    assert again.capability_names == ["delivery", "patrol"]

    assert len(await service.list()) == 1


async def test_mark_offline_only_touches_stale_idle_robots(uow_factory, clock, robot) -> None:
    service = RobotService(uow_factory, clock=clock)
    clock.advance(120)

    touched = await service.mark_offline(clock.moment)

    assert touched == 1
    refreshed = await service.get(robot.id)
    assert refreshed.status == RobotStatus.OFFLINE.value

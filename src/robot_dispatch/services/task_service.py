from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from robot_dispatch.config import Settings
from robot_dispatch.db.models import Robot, Task, TaskEvent, utcnow
from robot_dispatch.domain.enums import RobotStatus, TaskEventKind, TaskStatus
from robot_dispatch.domain.state_machine import can_transition, ensure_transition, is_cancellable
from robot_dispatch.logging_setup import get_logger
from robot_dispatch.repositories.protocols import UnitOfWorkFactory
from robot_dispatch.services.errors import RobotNotFound, TaskConflict, TaskNotFound

logger = get_logger("tasks")


@dataclass(frozen=True)
class CreateTaskCommand:
    type: str
    payload: dict
    priority: int = 100
    external_id: str | None = None
    max_attempts: int | None = None
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class CreateTaskResult:
    task: Task
    replayed: bool


class TaskService:
    def __init__(self, uow_factory: UnitOfWorkFactory, settings: Settings, *, clock=utcnow) -> None:
        self._uow_factory = uow_factory
        self._settings = settings
        self._clock = clock

    async def create(self, command: CreateTaskCommand) -> CreateTaskResult:
        """Create a task; `external_id` makes the call idempotent.

        The unique index on `tasks.external_id` is the source of truth: if two
        clients race with the same external id, the loser gets the winner's task
        back instead of a duplicate.
        """
        if command.external_id:
            async with self._uow_factory() as uow:
                existing = await uow.tasks.get_by_external_id(command.external_id)
                if existing is not None:
                    return CreateTaskResult(task=existing, replayed=True)

        task = Task.new(
            task_type=command.type,
            payload=command.payload,
            priority=command.priority,
            external_id=command.external_id,
            max_attempts=command.max_attempts or self._settings.default_max_attempts,
            timeout_seconds=command.timeout_seconds or self._settings.default_task_timeout_seconds,
            available_at=self._clock(),
        )
        try:
            async with self._uow_factory() as uow:
                await uow.tasks.add(task)
                await uow.events.add(
                    TaskEvent.new(
                        task_id=task.id,
                        kind=TaskEventKind.CREATED.value,
                        to_status=task.status,
                        message=f"task {task.type} queued",
                        payload={
                            "priority": task.priority,
                            "external_id": task.external_id,
                            "max_attempts": task.max_attempts,
                        },
                    )
                )
                await uow.commit()
        except IntegrityError:
            if not command.external_id:
                raise
            async with self._uow_factory() as uow:
                existing = await uow.tasks.get_by_external_id(command.external_id)
            if existing is None:  # pragma: no cover - unique violation without a row
                raise
            logger.info("task creation replayed after unique violation", external_id=command.external_id)
            return CreateTaskResult(task=existing, replayed=True)

        logger.info("task created", task_id=str(task.id), type=task.type, priority=task.priority)
        return CreateTaskResult(task=task, replayed=False)

    async def get(self, task_id: uuid.UUID) -> Task:
        async with self._uow_factory() as uow:
            task = await uow.tasks.get(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        return task

    async def list(
        self,
        *,
        statuses: list[str] | None = None,
        robot_id: uuid.UUID | None = None,
        task_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        async with self._uow_factory() as uow:
            return await uow.tasks.list(
                statuses=statuses,
                robot_id=robot_id,
                task_type=task_type,
                limit=limit,
                offset=offset,
            )

    async def events(self, task_id: uuid.UUID) -> list[TaskEvent]:
        async with self._uow_factory() as uow:
            return await uow.events.list_for_task(task_id)

    async def stats(self) -> dict[str, int]:
        async with self._uow_factory() as uow:
            return await uow.tasks.count_by_status()

    async def cancel(self, task_id: uuid.UUID) -> Task:
        now = self._clock()
        async with self._uow_factory() as uow:
            task = await uow.tasks.get(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            current = TaskStatus(task.status)
            if current.is_terminal:
                raise TaskConflict(task_id, current.value, "task already finished")
            if not is_cancellable(current):
                raise TaskConflict(
                    task_id,
                    current.value,
                    "running tasks cannot be cancelled from the API: the robot owns the execution",
                )
            if not can_transition(current, TaskStatus.CANCELLED):  # pragma: no cover - guard
                raise TaskConflict(task_id, current.value, "cancellation is not allowed")

            robot: Robot | None = await uow.robots.get(task.robot_id) if task.robot_id else None
            if robot is not None:
                robot.status = RobotStatus.IDLE.value
                robot.current_task_id = None
                robot.updated_at = now

            task.status = ensure_transition(current, TaskStatus.CANCELLED).value
            task.lease_expires_at = None
            task.finished_at = now
            task.updated_at = now
            task.version += 1
            await uow.events.add(
                TaskEvent.new(
                    task_id=task.id,
                    kind=TaskEventKind.CANCELLED.value,
                    from_status=current.value,
                    to_status=task.status,
                    robot_id=task.robot_id,
                    message="cancelled by API request",
                )
            )
            await uow.commit()
            return task


class RobotService:
    def __init__(self, uow_factory: UnitOfWorkFactory, *, clock=utcnow) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def register(
        self,
        *,
        name: str,
        namespace: str,
        capabilities: list[str],
    ) -> tuple[Robot, bool]:
        """Register or refresh a robot. Registration is idempotent by name."""
        now = self._clock()
        async with self._uow_factory() as uow:
            robot = await uow.robots.get_by_name(name)
            created = robot is None
            if robot is None:
                robot = Robot.new(
                    name=name,
                    namespace=namespace,
                    capabilities=capabilities,
                    status=RobotStatus.IDLE,
                    last_seen_at=now,
                )
                await uow.robots.add(robot)
            else:
                robot.namespace = namespace
                robot.set_capabilities(capabilities)
                robot.last_seen_at = now
                robot.updated_at = now
                if robot.current_task_id is None:
                    robot.status = RobotStatus.IDLE.value
            await uow.commit()
        logger.info("robot registered", robot=name, created=created, capabilities=capabilities)
        return robot, created

    async def get(self, robot_id: uuid.UUID) -> Robot:
        async with self._uow_factory() as uow:
            robot = await uow.robots.get(robot_id)
        if robot is None:
            raise RobotNotFound(robot_id)
        return robot

    async def list(self) -> list[Robot]:
        async with self._uow_factory() as uow:
            return await uow.robots.list()

    async def mark_offline(self, older_than: datetime) -> int:
        """Reaper helper: robots that stopped sending heartbeats become offline."""
        async with self._uow_factory() as uow:
            robots = await uow.robots.list()
            touched = 0
            for robot in robots:
                if robot.status == RobotStatus.IDLE.value and (
                    robot.last_seen_at is None or robot.last_seen_at < older_than
                ):
                    robot.status = RobotStatus.OFFLINE.value
                    robot.updated_at = older_than
                    touched += 1
            if touched:
                await uow.commit()
            return touched


def _event(task: Task, kind: TaskEventKind, **kwargs) -> TaskEvent:  # pragma: no cover - helper
    return TaskEvent.new(task_id=task.id, kind=kind.value, **kwargs)

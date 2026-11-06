from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta

from robot_dispatch.db.models import OutboxMessage, Robot, Task, TaskEvent
from robot_dispatch.domain.enums import QUEUED_TASK_STATUSES, RobotStatus


class Snapshot:
    __slots__ = ("tasks", "robots", "events", "outbox")

    def __init__(self, tasks: dict, robots: dict, events: list, outbox: list) -> None:
        self.tasks = tasks
        self.robots = robots
        self.events = events
        self.outbox = outbox


class InMemoryStore:
    """Process-local stand-in for PostgreSQL, used by unit tests."""

    def __init__(self) -> None:
        self.tasks: dict[uuid.UUID, Task] = {}
        self.robots: dict[uuid.UUID, Robot] = {}
        self.events: list[TaskEvent] = []
        self.outbox: list[OutboxMessage] = []

    def snapshot(self) -> Snapshot:
        return Snapshot(
            tasks=copy.deepcopy(self.tasks),
            robots=copy.deepcopy(self.robots),
            events=copy.deepcopy(self.events),
            outbox=copy.deepcopy(self.outbox),
        )

    def restore(self, snapshot: Snapshot) -> None:
        self.tasks = snapshot.tasks
        self.robots = snapshot.robots
        self.events = snapshot.events
        self.outbox = snapshot.outbox


class InMemoryTaskRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, task: Task) -> Task:
        self._store.tasks[task.id] = task
        return task

    async def get(self, task_id: uuid.UUID) -> Task | None:
        return self._store.tasks.get(task_id)

    async def get_by_external_id(self, external_id: str) -> Task | None:
        for task in self._store.tasks.values():
            if task.external_id == external_id:
                return task
        return None

    async def lock_ready(self, *, now: datetime, limit: int) -> list[Task]:
        queued = [
            task
            for task in self._store.tasks.values()
            if task.status in {status.value for status in QUEUED_TASK_STATUSES}
            and task.available_at <= now
        ]
        queued.sort(key=lambda task: (-task.priority, task.available_at, task.created_at))
        return queued[:limit]

    async def lock_expired_leases(self, *, now: datetime, limit: int) -> list[Task]:
        expired = [
            task
            for task in self._store.tasks.values()
            if task.status in {"pending", "retrying", "assigned", "running"}
            and task.lease_expires_at is not None
            and task.lease_expires_at < now
        ]
        expired.sort(key=lambda task: task.lease_expires_at)
        return expired[:limit]

    async def list(
        self,
        *,
        statuses: list[str] | None = None,
        robot_id: uuid.UUID | None = None,
        task_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        items = list(self._store.tasks.values())
        if statuses:
            items = [task for task in items if task.status in statuses]
        if robot_id is not None:
            items = [task for task in items if task.robot_id == robot_id]
        if task_type is not None:
            items = [task for task in items if task.type == task_type]
        items.sort(key=lambda task: task.created_at, reverse=True)
        return items[offset : offset + limit]

    async def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self._store.tasks.values():
            counts[task.status] = counts.get(task.status, 0) + 1
        return counts


class InMemoryRobotRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, robot: Robot) -> Robot:
        self._store.robots[robot.id] = robot
        return robot

    async def get(self, robot_id: uuid.UUID) -> Robot | None:
        return self._store.robots.get(robot_id)

    async def get_by_name(self, name: str) -> Robot | None:
        for robot in self._store.robots.values():
            if robot.name == name:
                return robot
        return None

    async def list(self) -> list[Robot]:
        return sorted(self._store.robots.values(), key=lambda robot: robot.name)

    async def find_idle_for(
        self, *, task_type: str, now: datetime, offline_after: int
    ) -> Robot | None:
        threshold = now - timedelta(seconds=offline_after)
        candidates = [
            robot
            for robot in self._store.robots.values()
            if robot.status == RobotStatus.IDLE.value
            and robot.last_seen_at is not None
            and robot.last_seen_at >= threshold
            and robot.supports(task_type)
        ]
        candidates.sort(key=lambda robot: robot.last_seen_at, reverse=True)
        return candidates[0] if candidates else None


class InMemoryEventRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, event: TaskEvent) -> TaskEvent:
        self._store.events.append(event)
        return event

    async def list_for_task(self, task_id: uuid.UUID, *, limit: int = 200) -> list[TaskEvent]:
        items = [event for event in self._store.events if event.task_id == task_id]
        items.sort(key=lambda event: event.created_at)
        return items[:limit]


class InMemoryOutboxRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, message: OutboxMessage) -> OutboxMessage:
        self._store.outbox.append(message)
        return message

    async def lock_pending(self, *, now: datetime, limit: int) -> list[OutboxMessage]:
        pending = [
            message
            for message in self._store.outbox
            if message.sent_at is None and message.available_at <= now
        ]
        pending.sort(key=lambda message: message.created_at)
        return pending[:limit]

    async def mark_sent(self, message: OutboxMessage, sent_at: datetime) -> None:
        message.sent_at = sent_at
        message.attempts += 1

    async def mark_failed(
        self, message: OutboxMessage, error: str, available_at: datetime, attempts: int
    ) -> None:
        message.attempts = attempts
        message.last_error = error[:2000]
        message.available_at = available_at


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._snapshot: Snapshot | None = None
        self.tasks = InMemoryTaskRepository(store)
        self.robots = InMemoryRobotRepository(store)
        self.events = InMemoryEventRepository(store)
        self.outbox = InMemoryOutboxRepository(store)

    async def __aenter__(self) -> InMemoryUnitOfWork:
        self._snapshot = self._store.snapshot()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._snapshot is not None:
            self._store.restore(self._snapshot)
            self._snapshot = None

    async def commit(self) -> None:
        self._snapshot = None

    async def rollback(self) -> None:
        if self._snapshot is not None:
            self._store.restore(self._snapshot)
            self._snapshot = None


class InMemoryUnitOfWorkFactory:
    def __init__(self, store: InMemoryStore | None = None) -> None:
        self.store = store or InMemoryStore()

    def __call__(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.store)

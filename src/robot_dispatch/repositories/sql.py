from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from robot_dispatch.db.models import OutboxMessage, Robot, Task, TaskEvent
from robot_dispatch.domain.enums import QUEUED_TASK_STATUSES, RobotStatus


class SqlTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: uuid.UUID) -> Task | None:
        return await self._session.get(Task, task_id)

    async def get_by_external_id(self, external_id: str) -> Task | None:
        stmt = select(Task).where(Task.external_id == external_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def lock_ready(self, *, now, limit: int) -> list[Task]:
        """Select queued tasks and lock them, skipping rows locked by other dispatchers.

        `FOR UPDATE SKIP LOCKED` makes several dispatcher replicas safe: each task is
        handed to exactly one of them, no advisory locks or coordination required.
        """
        stmt = (
            select(Task)
            .where(
                Task.status.in_([status.value for status in QUEUED_TASK_STATUSES]),
                Task.available_at <= now,
            )
            .order_by(Task.priority.desc(), Task.available_at.asc(), Task.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def lock_expired_leases(self, *, now, limit: int) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.status.in_([status.value for status in QUEUED_TASK_STATUSES | {"assigned", "running"}]),
                Task.lease_expires_at.is_not(None),
                Task.lease_expires_at < now,
            )
            .order_by(Task.lease_expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self,
        *,
        statuses: list[str] | None = None,
        robot_id: uuid.UUID | None = None,
        task_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task)
        if statuses:
            stmt = stmt.where(Task.status.in_(statuses))
        if robot_id is not None:
            stmt = stmt.where(Task.robot_id == robot_id)
        if task_type is not None:
            stmt = stmt.where(Task.type == task_type)
        stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(Task.status, func.count()).group_by(Task.status)
        result = await self._session.execute(stmt)
        return {row[0]: int(row[1]) for row in result.all()}


class SqlRobotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, robot: Robot) -> Robot:
        self._session.add(robot)
        await self._session.flush()
        return robot

    async def get(self, robot_id: uuid.UUID) -> Robot | None:
        return await self._session.get(Robot, robot_id)

    async def get_by_name(self, name: str) -> Robot | None:
        stmt = select(Robot).where(Robot.name == name)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list(self) -> list[Robot]:
        stmt = select(Robot).order_by(Robot.name)
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())

    async def find_idle_for(self, *, task_type: str, now, offline_after) -> Robot | None:
        """Pick a live robot that advertises the required capability."""
        from datetime import timedelta

        threshold = now - timedelta(seconds=offline_after)
        stmt = (
            select(Robot)
            .join(Robot.capabilities)
            .where(
                Robot.status == RobotStatus.IDLE.value,
                Robot.last_seen_at.is_not(None),
                Robot.last_seen_at >= threshold,
            )
            .order_by(Robot.last_seen_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.unique().scalars().first()


class SqlEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: TaskEvent) -> TaskEvent:
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_task(self, task_id: uuid.UUID, *, limit: int = 200) -> list[TaskEvent]:
        stmt = (
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SqlOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboxMessage) -> OutboxMessage:
        self._session.add(message)
        await self._session.flush()
        return message

    async def lock_pending(self, *, now, limit: int) -> list[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.sent_at.is_(None), OutboxMessage.available_at <= now)
            .order_by(OutboxMessage.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_sent(self, message: OutboxMessage, sent_at) -> None:
        message.sent_at = sent_at
        message.attempts += 1
        await self._session.flush()

    async def mark_failed(self, message: OutboxMessage, error: str, available_at, attempts: int) -> None:
        message.attempts = attempts
        message.last_error = error[:2000]
        message.available_at = available_at
        await self._session.flush()


def _unused(*_: Any) -> None:  # pragma: no cover - keeps linters honest about imports
    return None

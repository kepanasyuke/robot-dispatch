from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from robot_dispatch.db.base import Base
from robot_dispatch.domain.enums import RobotStatus, TaskStatus

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class RobotCapability(Base):
    __tablename__ = "robot_capabilities"

    robot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("robots.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(64), primary_key=True)

    robot: Mapped[Robot] = relationship(back_populates="capabilities")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RobotCapability {self.name}>"


class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RobotStatus.OFFLINE.value, index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    capabilities: Mapped[list[RobotCapability]] = relationship(
        back_populates="robot", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_robots_status_seen", "status", "last_seen_at"),)

    @property
    def capability_names(self) -> list[str]:
        return sorted(capability.name for capability in self.capabilities)

    def supports(self, task_type: str) -> bool:
        return any(capability.name == task_type for capability in self.capabilities)

    def set_capabilities(self, names: list[str]) -> None:
        self.capabilities = [RobotCapability(name=name) for name in sorted(set(names))]

    @classmethod
    def new(
        cls,
        *,
        name: str,
        namespace: str,
        capabilities: list[str],
        status: RobotStatus = RobotStatus.OFFLINE,
        last_seen_at: datetime | None = None,
    ) -> Robot:
        now = utcnow()
        robot = cls(
            id=uuid.uuid4(),
            name=name,
            namespace=namespace,
            status=status.value,
            last_seen_at=last_seen_at,
            created_at=now,
            updated_at=now,
        )
        robot.set_capabilities(capabilities)
        return robot

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Robot {self.name} {self.status}>"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TaskStatus.PENDING.value, index=True
    )

    robot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("robots.id", ondelete="SET NULL"), nullable=True
    )
    command_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)

    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_tasks_dispatch_queue", "status", "priority", "available_at"),
        Index("ix_tasks_robot_status", "robot_id", "status"),
        Index("ix_tasks_lease", "status", "lease_expires_at"),
    )

    @property
    def status_enum(self) -> TaskStatus:
        return TaskStatus(self.status)

    @classmethod
    def new(
        cls,
        *,
        task_type: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        external_id: str | None = None,
        max_attempts: int = 3,
        timeout_seconds: int = 120,
        available_at: datetime | None = None,
    ) -> Task:
        now = utcnow()
        return cls(
            id=uuid.uuid4(),
            external_id=external_id,
            type=task_type,
            payload=payload or {},
            priority=priority,
            status=TaskStatus.PENDING.value,
            attempts=0,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            available_at=available_at or now,
            created_at=now,
            updated_at=now,
            version=0,
        )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Task {self.type} {self.status} attempts={self.attempts}>"


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    robot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @classmethod
    def new(
        cls,
        *,
        task_id: uuid.UUID,
        kind: str,
        from_status: str | None = None,
        to_status: str | None = None,
        robot_id: uuid.UUID | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TaskEvent:
        return cls(
            id=uuid.uuid4(),
            task_id=task_id,
            kind=kind,
            from_status=from_status,
            to_status=to_status,
            robot_id=robot_id,
            message=message,
            payload=payload or {},
            created_at=utcnow(),
        )


class OutboxMessage(Base):
    """Transactional outbox: rows are written in the same transaction as the state change."""

    __tablename__ = "outbox_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exchange: Mapped[str] = mapped_column(String(64), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    headers: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expiration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_outbox_pending", "sent_at", "available_at"),)

    @classmethod
    def new(
        cls,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        message_id: str,
        headers: dict[str, Any] | None = None,
        expiration_ms: int | None = None,
    ) -> OutboxMessage:
        now = utcnow()
        return cls(
            id=uuid.uuid4(),
            exchange=exchange,
            routing_key=routing_key,
            payload=payload,
            headers=headers or {},
            message_id=message_id,
            expiration_ms=expiration_ms,
            attempts=0,
            available_at=now,
            created_at=now,
        )

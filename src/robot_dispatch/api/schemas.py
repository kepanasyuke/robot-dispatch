from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from robot_dispatch.domain.enums import TaskStatus


class TaskCreateRequest(BaseModel):
    type: str = Field(min_length=1, max_length=64, examples=["delivery"])
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=1000, description="Higher value is dispatched first")
    external_id: str | None = Field(
        default=None,
        max_length=128,
        description="Caller-side idempotency key (or send the Idempotency-Key header)",
    )
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    timeout_seconds: int | None = Field(
        default=None, ge=1, le=86_400, description="Lease duration for a single attempt"
    )

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("type must not be blank")
        return normalized

    @field_validator("external_id")
    @classmethod
    def _strip_external_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    status: TaskStatus
    priority: int
    payload: dict[str, Any]
    external_id: str | None
    robot_id: UUID | None
    command_id: UUID | None
    attempts: int
    max_attempts: int
    timeout_seconds: int
    available_at: datetime
    lease_expires_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    version: int


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    limit: int
    offset: int


class TaskEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    kind: str
    from_status: str | None
    to_status: str | None
    robot_id: UUID | None
    message: str | None
    payload: dict[str, Any]
    created_at: datetime


class RobotRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128, examples=["robot-1"])
    namespace: str = Field(min_length=1, max_length=128, examples=["/robot1"])
    capabilities: list[str] = Field(
        default_factory=lambda: ["delivery"],
        description="Task types this robot can execute",
    )

    @field_validator("capabilities")
    @classmethod
    def _normalize_capabilities(cls, value: list[str]) -> list[str]:
        cleaned = sorted({item.strip().lower() for item in value if item.strip()})
        if not cleaned:
            raise ValueError("at least one capability is required")
        return cleaned


class RobotResponse(BaseModel):
    id: UUID
    name: str
    namespace: str
    status: str
    capabilities: list[str]
    last_seen_at: datetime | None
    current_task_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_robot(cls, robot) -> RobotResponse:
        return cls(
            id=robot.id,
            name=robot.name,
            namespace=robot.namespace,
            status=robot.status,
            capabilities=robot.capability_names,
            last_seen_at=robot.last_seen_at,
            current_task_id=robot.current_task_id,
            created_at=robot.created_at,
            updated_at=robot.updated_at,
        )


class RobotListResponse(BaseModel):
    items: list[RobotResponse]


class StatsResponse(BaseModel):
    tasks: dict[str, int]
    task_total: int
    robots: dict[str, int]
    queues: dict[str, int | None]


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str]

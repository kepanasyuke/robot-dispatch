from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

COMMANDS_EXCHANGE = "robot.commands"
EVENTS_EXCHANGE = "robot.events"
DLX_EXCHANGE = "dispatch.dlx"
RESULTS_QUEUE = "dispatch.results"
RETRY_QUEUE = "dispatch.results.retry"
DLQ_QUEUE = "dispatch.results.dlq"


def command_routing_key(robot_id: UUID) -> str:
    return f"command.{robot_id}"


def command_queue_name(robot_id: UUID) -> str:
    return f"cmd.{robot_id}"


def result_routing_key(robot_id: UUID) -> str:
    return f"result.{robot_id}"


def heartbeat_routing_key(robot_id: UUID) -> str:
    return f"heartbeat.{robot_id}"


class CommandMessage(BaseModel):
    """Server -> robot. Sent exactly once per attempt, deduplicated by command_id."""

    kind: Literal["command"] = "command"
    command_id: UUID
    task_id: UUID
    task_type: str
    robot_id: UUID
    namespace: str
    attempt: int
    timeout_seconds: int
    payload: dict[str, Any] = Field(default_factory=dict)
    issued_at: datetime


class TaskResultMessage(BaseModel):
    """Robot -> server. `event=progress` keeps the lease alive."""

    kind: Literal["result"] = "result"
    event: Literal["progress", "succeeded", "failed"]
    task_id: UUID
    robot_id: UUID
    command_id: UUID | None = None
    progress: float | None = None
    detail: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    occurred_at: datetime


class HeartbeatMessage(BaseModel):
    kind: Literal["heartbeat"] = "heartbeat"
    robot_id: UUID
    namespace: str | None = None
    status: Literal["idle", "busy", "offline"] | None = None
    battery: float | None = None
    occurred_at: datetime

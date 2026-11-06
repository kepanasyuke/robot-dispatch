"""gRPC implementation of the fleet control plane.

Transport-level concerns stay here: input validation, mapping domain errors to
canonical gRPC status codes, idempotent command dispatch and deadline checks.
The registry knows nothing about protobuf, so the same rules can back a REST
endpoint without duplication.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import NoReturn

import grpc

from grpc_fleet_api import fleet_pb2
from grpc_fleet_api.registry import FleetRegistry, RobotRecord, utcnow

VALID_STATUSES = {"idle", "busy", "offline"}
MAX_LIST_LIMIT = 500
MAX_FUTURE_HEARTBEAT = timedelta(seconds=30)


class FleetService:
    """Servicer; registered through `fleet_pb2_grpc.add_FleetServiceServicer_to_server`."""

    def __init__(self, registry: FleetRegistry, *, clock=utcnow) -> None:
        self._registry = registry
        self._clock = clock
        self._commands: dict[str, str] = {}

    def _abort(self, context: grpc.ServicerContext, code: grpc.StatusCode, detail: str) -> NoReturn:
        context.abort(code, detail)
        raise AssertionError("context.abort must raise")

    def _require_text(self, value: str, field: str, context: grpc.ServicerContext) -> None:
        if not value or not value.strip():
            self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, f"{field} must not be empty")

    def _deadline_expired(self, context: grpc.ServicerContext) -> bool:
        remaining = context.time_remaining()
        return remaining is not None and remaining <= 0

    def GetRobot(self, request: fleet_pb2.GetRobotRequest, context) -> fleet_pb2.Robot:
        self._require_text(request.robot_id, "robot_id", context)
        if self._deadline_expired(context):
            self._abort(context, grpc.StatusCode.DEADLINE_EXCEEDED, "deadline already expired")

        record = self._registry.get(request.robot_id)
        if record is None:
            self._abort(context, grpc.StatusCode.NOT_FOUND, f"robot {request.robot_id} is unknown")
        return _to_proto(record, self._registry.effective_status(record))

    def ListRobots(
        self, request: fleet_pb2.ListRobotsRequest, context
    ) -> fleet_pb2.ListRobotsResponse:
        if request.status and request.status not in VALID_STATUSES:
            self._abort(
                context,
                grpc.StatusCode.INVALID_ARGUMENT,
                f"status must be one of {sorted(VALID_STATUSES)} or empty",
            )
        if request.limit < 0 or request.limit > MAX_LIST_LIMIT:
            self._abort(
                context, grpc.StatusCode.INVALID_ARGUMENT, f"limit must be 0..{MAX_LIST_LIMIT}"
            )
        limit = request.limit or 100
        robots = self._registry.list(status=request.status or None, limit=limit)
        return fleet_pb2.ListRobotsResponse(
            robots=[_to_proto(robot, self._registry.effective_status(robot)) for robot in robots]
        )

    def ReportHeartbeat(
        self, request: fleet_pb2.HeartbeatRequest, context
    ) -> fleet_pb2.HeartbeatResponse:
        self._require_text(request.robot_id, "robot_id", context)
        if request.battery_percent < 0 or request.battery_percent > 100:
            self._abort(
                context,
                grpc.StatusCode.INVALID_ARGUMENT,
                "battery_percent must be within 0..100",
            )
        if request.status and request.status not in VALID_STATUSES:
            self._abort(
                context,
                grpc.StatusCode.INVALID_ARGUMENT,
                f"status must be one of {sorted(VALID_STATUSES)}",
            )

        at = _from_unix_ms(request.at_unix_ms) if request.at_unix_ms else self._clock()
        if at - self._clock() > MAX_FUTURE_HEARTBEAT:
            self._abort(
                context, grpc.StatusCode.INVALID_ARGUMENT, "heartbeat timestamp is in the future"
            )

        record = self._registry.heartbeat(
            request.robot_id,
            status=request.status or None,
            battery_percent=request.battery_percent or None,
        )
        if record is None:
            self._abort(
                context, grpc.StatusCode.NOT_FOUND, f"robot {request.robot_id} is unknown"
            )
        return fleet_pb2.HeartbeatResponse(
            accepted=True, server_time_unix_ms=_to_unix_ms(self._clock())
        )

    def DispatchTask(
        self, request: fleet_pb2.DispatchTaskRequest, context
    ) -> fleet_pb2.DispatchTaskResponse:
        self._require_text(request.task_id, "task_id", context)
        self._require_text(request.command_id, "command_id", context)
        self._require_text(request.task_type, "task_type", context)
        if request.timeout_seconds <= 0 or request.timeout_seconds > 86_400:
            self._abort(
                context, grpc.StatusCode.INVALID_ARGUMENT, "timeout_seconds must be 1..86400"
            )

        known = self._commands.get(request.command_id)
        if known is not None:
            return fleet_pb2.DispatchTaskResponse(
                command_id=request.command_id, duplicate=True, assigned_robot_id=known
            )

        robot = self._registry.find_idle(
            request.task_type, preferred=request.robot_id or None
        )
        if robot is None:
            self._abort(
                context,
                grpc.StatusCode.FAILED_PRECONDITION,
                f"no idle robot can execute {request.task_type}",
            )

        self._registry.mark_busy(robot.id)
        self._commands[request.command_id] = robot.id
        return fleet_pb2.DispatchTaskResponse(
            command_id=request.command_id, duplicate=False, assigned_robot_id=robot.id
        )


def _to_proto(record: RobotRecord, status: str) -> fleet_pb2.Robot:
    return fleet_pb2.Robot(
        id=record.id,
        name=record.name,
        status=status,
        capabilities=sorted(record.capabilities),
        battery_percent=record.battery_percent,
        last_seen_unix_ms=_to_unix_ms(record.last_seen),
    )


def _to_unix_ms(moment: datetime | None) -> int:
    if moment is None:
        return 0
    return int(moment.timestamp() * 1000)


def _from_unix_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def register(service: FleetService, server: grpc.Server) -> None:
    """Explicit registration helper, avoids importing generated stubs everywhere."""
    from grpc_fleet_api import fleet_pb2_grpc

    fleet_pb2_grpc.add_FleetServiceServicer_to_server(service, server)


def now_ms() -> int:  # pragma: no cover - helper for scripts
    return int(time.time() * 1000)

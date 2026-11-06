from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import grpc
import pytest
from grpc_fleet_api import fleet_pb2, fleet_pb2_grpc
from grpc_fleet_api.interceptors import MetricsRegistry
from grpc_fleet_api.registry import FleetRegistry
from grpc_fleet_api.server import create_server
from grpc_fleet_api.service import FleetService

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, moment: datetime = BASE_TIME) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> datetime:
        self.moment += timedelta(seconds=seconds)
        return self.moment


@pytest.fixture
def env():
    clock = FakeClock()
    registry = FleetRegistry(clock=clock)
    registry.upsert_robot("robot-1", name="Robot 1", capabilities={"delivery"}, status="idle")
    registry.upsert_robot("robot-2", name="Robot 2", capabilities={"patrol"}, status="idle")

    metrics = MetricsRegistry()
    service = FleetService(registry, clock=clock)
    server = create_server(service, port=0, metrics=metrics).start()
    channel = grpc.insecure_channel(server.address)
    grpc.channel_ready_future(channel).result(timeout=5)

    yield SimpleNamespace(
        stub=fleet_pb2_grpc.FleetServiceStub(channel),
        registry=registry,
        clock=clock,
        metrics=metrics,
        server=server,
    )

    channel.close()
    server.stop(0)


def dispatch_request(command_id: str = "cmd-1", **overrides) -> fleet_pb2.DispatchTaskRequest:
    payload = {
        "task_id": "task-1",
        "command_id": command_id,
        "task_type": "delivery",
        "timeout_seconds": 30,
    }
    payload.update(overrides)
    return fleet_pb2.DispatchTaskRequest(**payload)


def test_get_robot_returns_contract_fields(env) -> None:
    robot = env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id="robot-1"))

    assert robot.id == "robot-1"
    assert robot.name == "Robot 1"
    assert robot.status == "idle"
    assert robot.capabilities == ["delivery"]
    assert robot.last_seen_unix_ms > 0


def test_get_unknown_robot_is_not_found(env) -> None:
    with pytest.raises(grpc.RpcError) as error:
        env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id="ghost"))

    assert error.value.code() == grpc.StatusCode.NOT_FOUND


def test_empty_robot_id_is_invalid(env) -> None:
    with pytest.raises(grpc.RpcError) as error:
        env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id=""))

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_list_robots_filters_by_status(env) -> None:
    env.stub.ReportHeartbeat(
        fleet_pb2.HeartbeatRequest(robot_id="robot-1", status="busy", battery_percent=55.0)
    )

    busy = env.stub.ListRobots(fleet_pb2.ListRobotsRequest(status="busy"))
    everything = env.stub.ListRobots(fleet_pb2.ListRobotsRequest())

    assert [robot.id for robot in busy.robots] == ["robot-1"]
    assert len(everything.robots) == 2
    assert everything.robots[0].battery_percent in {0.0, 55.0}


def test_list_robots_validates_status_and_limit(env) -> None:
    with pytest.raises(grpc.RpcError) as bad_status:
        env.stub.ListRobots(fleet_pb2.ListRobotsRequest(status="sleeping"))
    with pytest.raises(grpc.RpcError) as bad_limit:
        env.stub.ListRobots(fleet_pb2.ListRobotsRequest(limit=10_000))

    assert bad_status.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert bad_limit.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_heartbeat_updates_battery_and_status(env) -> None:
    response = env.stub.ReportHeartbeat(
        fleet_pb2.HeartbeatRequest(robot_id="robot-1", status="idle", battery_percent=71.5)
    )

    assert response.accepted is True
    assert response.server_time_unix_ms > 0
    robot = env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id="robot-1"))
    assert robot.battery_percent == 71.5


def test_heartbeat_rejects_out_of_range_battery(env) -> None:
    with pytest.raises(grpc.RpcError) as error:
        env.stub.ReportHeartbeat(
            fleet_pb2.HeartbeatRequest(robot_id="robot-1", battery_percent=150.0)
        )

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_heartbeat_from_unknown_robot_is_not_found(env) -> None:
    with pytest.raises(grpc.RpcError) as error:
        env.stub.ReportHeartbeat(fleet_pb2.HeartbeatRequest(robot_id="ghost"))

    assert error.value.code() == grpc.StatusCode.NOT_FOUND


def test_silent_robot_is_reported_offline(env) -> None:
    env.clock.advance(120)

    robot = env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id="robot-1"))

    assert robot.status == "offline"


def test_dispatch_assigns_capable_robot(env) -> None:
    response = env.stub.DispatchTask(dispatch_request())

    assert response.duplicate is False
    assert response.assigned_robot_id == "robot-1"
    assert response.command_id == "cmd-1"


def test_repeated_command_id_is_idempotent(env) -> None:
    first = env.stub.DispatchTask(dispatch_request("cmd-9"))
    second = env.stub.DispatchTask(dispatch_request("cmd-9"))

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.assigned_robot_id == first.assigned_robot_id


def test_dispatch_without_capable_robot_fails_precondition(env) -> None:
    with pytest.raises(grpc.RpcError) as error:
        env.stub.DispatchTask(dispatch_request(task_type="inspection"))

    assert error.value.code() == grpc.StatusCode.FAILED_PRECONDITION


def test_dispatch_respects_preferred_robot(env) -> None:
    with pytest.raises(grpc.RpcError) as error:
        env.stub.DispatchTask(dispatch_request(robot_id="robot-2"))

    assert error.value.code() == grpc.StatusCode.FAILED_PRECONDITION


def test_dispatch_validates_identifiers(env) -> None:
    with pytest.raises(grpc.RpcError) as empty_command:
        env.stub.DispatchTask(dispatch_request(command_id=""))
    with pytest.raises(grpc.RpcError) as bad_timeout:
        env.stub.DispatchTask(dispatch_request(timeout_seconds=0))

    assert empty_command.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert bad_timeout.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_metrics_are_recorded_per_method(env) -> None:
    env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id="robot-1"))
    with pytest.raises(grpc.RpcError):
        env.stub.GetRobot(fleet_pb2.GetRobotRequest(robot_id="ghost"))

    snapshot = env.metrics.snapshot()

    assert snapshot["GetRobot"]["calls"] == 2
    assert snapshot["GetRobot"]["ok"] == 1
    assert snapshot["GetRobot"]["error"] == 1
    assert snapshot["GetRobot"]["avg_ms"] >= 0
    assert env.metrics.total_calls == 2

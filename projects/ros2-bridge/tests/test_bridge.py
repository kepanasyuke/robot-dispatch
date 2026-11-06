from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta

import pytest
from ros2_bridge.bridge import BridgeTimeout, RosBridge
from ros2_bridge.contracts import TaskCommandPayload
from ros2_bridge.transport import FakeTransport

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
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def bridge(transport, clock) -> RosBridge:
    return RosBridge("robot1", transport, clock=clock)


def stamp_at(clock: FakeClock, offset: float = 0.0) -> dict:
    moment = clock.moment + timedelta(seconds=offset)
    return {"sec": int(moment.timestamp()), "nanosec": 0}


def header_at(clock: FakeClock, offset: float = 0.0, frame_id: str = "map") -> dict:
    return {"stamp": stamp_at(clock, offset), "frame_id": frame_id}


def odom(clock: FakeClock, *, x: float = 1.0, y: float = 2.0, yaw: float = 0.0, offset: float = 0.0) -> dict:
    return {
        "header": header_at(clock, offset),
        "pose": {
            "position": {"x": x, "y": y, "z": 0.0},
            "orientation": {
                "x": 0.0,
                "y": 0.0,
                "z": math.sin(yaw / 2),
                "w": math.cos(yaw / 2),
            },
        },
        "twist": {
            "linear": {"x": 0.6, "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": 0.25},
        },
    }


def battery(clock: FakeClock, percentage: float = 0.87) -> dict:
    return {
        "header": header_at(clock),
        "percentage": percentage,
        "voltage": 24.2,
        "present": True,
    }


def feedback(command_id: str = "cmd-1", state: str = "succeeded", **overrides) -> dict:
    payload = {
        "header": {"stamp": {"sec": 0, "nanosec": 0}, "frame_id": "map"},
        "task_id": "task-1",
        "command_id": command_id,
        "state": state,
        "progress": 100.0,
        "detail": "delivered",
        "error": None,
    }
    payload.update(overrides)
    return payload


def command(command_id: str = "cmd-1") -> TaskCommandPayload:
    return TaskCommandPayload(
        command_id=command_id,
        task_id="task-1",
        task_type="delivery",
        timeout_seconds=30,
        payload={"target": "a"},
        issued_at=BASE_TIME,
    )


async def test_start_subscribes_to_robot_topics(bridge, transport) -> None:
    await bridge.start()

    assert transport.subscriptions == [
        "/robot1/odom",
        "/robot1/battery_state",
        "/robot1/task_feedback",
    ]


async def test_odometry_updates_telemetry(bridge, transport, clock) -> None:
    await bridge.start()

    await transport.inject("/robot1/odom", odom(clock, x=1.5, y=-2.0, yaw=math.pi / 2))

    telemetry = bridge.telemetry()
    assert telemetry is not None
    assert (telemetry.x, telemetry.y) == (1.5, -2.0)
    assert telemetry.yaw_rad == pytest.approx(math.pi / 2, abs=1e-3)
    assert telemetry.speed_mps == 0.6
    assert telemetry.frame_id == "map"


async def test_battery_percentage_is_normalized(bridge, transport, clock) -> None:
    await bridge.start()
    await transport.inject("/robot1/odom", odom(clock))

    await transport.inject("/robot1/battery_state", battery(clock, 0.87))

    telemetry = bridge.telemetry()
    assert telemetry is not None
    assert telemetry.battery_percent == 87.0


async def test_out_of_spec_battery_is_counted_not_applied(bridge, transport, clock) -> None:
    await bridge.start()

    await transport.inject("/robot1/battery_state", battery(clock, 87.0))

    assert bridge.stats.invalid_payloads == 1
    assert bridge.telemetry() is None


async def test_stale_odometry_does_not_rewind_state(bridge, transport, clock) -> None:
    await bridge.start()
    await transport.inject("/robot1/odom", odom(clock, x=5.0))
    clock.advance(120)

    await transport.inject("/robot1/odom", odom(clock, x=1.0, offset=-60))

    telemetry = bridge.telemetry()
    assert telemetry is not None
    assert telemetry.x == 5.0
    assert bridge.stats.stale_messages == 1


async def test_future_timestamp_is_rejected(bridge, transport, clock) -> None:
    await bridge.start()

    await transport.inject("/robot1/odom", odom(clock, offset=600))

    assert bridge.telemetry() is None
    assert bridge.stats.stale_messages == 1


async def test_unknown_and_foreign_topics_are_ignored(bridge, transport, clock) -> None:
    await bridge.start()

    bridge.handle_message("/robot1/imu", {"any": "payload"})
    bridge.handle_message("/robot2/odom", odom(clock))

    assert bridge.stats.unknown_topics == 2
    assert bridge.telemetry() is None


async def test_command_is_published_once(bridge, transport) -> None:
    first = await bridge.publish_command(command("cmd-7"))
    second = await bridge.publish_command(command("cmd-7"))

    assert first.duplicate is False
    assert second.duplicate is True
    assert len(transport.published) == 1
    topic, payload = transport.published[0]
    assert topic == "/robot1/task_command"
    assert payload["command_id"] == "cmd-7"
    assert payload["payload"] == {"target": "a"}
    assert bridge.stats.commands_published == 1
    assert bridge.stats.duplicate_commands == 1


async def test_command_dedup_expires_after_ttl(bridge, transport, clock) -> None:
    await bridge.publish_command(command("cmd-7"))
    clock.advance(11 * 60)

    receipt = await bridge.publish_command(command("cmd-7"))

    assert receipt.duplicate is False
    assert len(transport.published) == 2


async def test_publish_failure_is_reported(bridge, transport) -> None:
    transport.fail_next_publish = RuntimeError("dds is down")

    with pytest.raises(RuntimeError):
        await bridge.publish_command(command("cmd-1"))

    assert bridge.stats.publish_failures == 1
    assert bridge.stats.commands_published == 0


async def test_wait_feedback_resolves_on_success(bridge, transport) -> None:
    await bridge.start()
    waiter = asyncio.create_task(bridge.wait_feedback("cmd-1", timeout_seconds=1.0))
    await transport.inject("/robot1/task_feedback", feedback("cmd-1", "running", progress=40.0))
    await transport.inject("/robot1/task_feedback", feedback("cmd-1", "succeeded"))

    record = await waiter

    assert record.state == "succeeded"
    assert len(bridge.feedback_history("cmd-1")) == 2


async def test_wait_feedback_times_out(bridge) -> None:
    with pytest.raises(BridgeTimeout):
        await bridge.wait_feedback("cmd-missing", timeout_seconds=0.05)


async def test_feedback_received_before_wait_is_returned(bridge, transport) -> None:
    await bridge.start()
    await transport.inject("/robot1/task_feedback", feedback("cmd-3", "failed", error="blocked"))

    record = await bridge.wait_feedback("cmd-3", timeout_seconds=0.1)

    assert record.state == "failed"
    assert record.error == "blocked"

"""Server <-> ROS2 bridge for one robot.

Responsibilities:

* subscribe to the robot's topics and normalize messages into `RobotTelemetry`;
* publish task commands with a `command_id` so a redelivered command is ignored
  by the robot's mission node;
* match asynchronous feedback to the waiting caller with a timeout, because a
  lost `succeeded` must not hang the dispatch service forever;
* drop messages with implausible timestamps (clock skew, stale packets from a
  previous session) instead of poisoning the robot state.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ros2_bridge.contracts import (
    BatteryStateMessage,
    OdometryMessage,
    RobotTelemetry,
    TaskCommandPayload,
    TaskFeedbackMessage,
)
from ros2_bridge.topics import InvalidPayload, TopicRegistry, UnknownTopic
from ros2_bridge.transport import MessageHandler, Transport

DEFAULT_COMMAND_TTL = timedelta(minutes=10)
DEFAULT_MAX_CLOCK_SKEW = timedelta(seconds=30)


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class BridgeTimeout(TimeoutError):
    def __init__(self, command_id: str, timeout: float) -> None:
        self.command_id = command_id
        self.timeout = timeout
        super().__init__(f"no feedback for command {command_id} within {timeout:.1f}s")


@dataclass(frozen=True)
class PublishReceipt:
    command_id: str
    topic: str
    duplicate: bool


@dataclass
class FeedbackRecord:
    command_id: str
    task_id: str
    state: str
    progress: float | None
    detail: str | None
    error: str | None
    received_at: datetime


@dataclass
class BridgeStats:
    messages: int = 0
    unknown_topics: int = 0
    invalid_payloads: int = 0
    stale_messages: int = 0
    commands_published: int = 0
    duplicate_commands: int = 0
    feedback_received: int = 0
    publish_failures: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "messages": self.messages,
            "unknown_topics": self.unknown_topics,
            "invalid_payloads": self.invalid_payloads,
            "stale_messages": self.stale_messages,
            "commands_published": self.commands_published,
            "duplicate_commands": self.duplicate_commands,
            "feedback_received": self.feedback_received,
            "publish_failures": self.publish_failures,
        }


@dataclass
class _State:
    stamp: datetime | None = None
    frame_id: str = "map"
    x: float = 0.0
    y: float = 0.0
    yaw_rad: float = 0.0
    speed_mps: float = 0.0
    angular_speed_rps: float = 0.0
    battery_percent: float = 0.0


class RosBridge:
    def __init__(
        self,
        robot_id: str,
        transport: Transport,
        *,
        registry: TopicRegistry | None = None,
        clock=utcnow,
        command_ttl: timedelta = DEFAULT_COMMAND_TTL,
        max_clock_skew: timedelta = DEFAULT_MAX_CLOCK_SKEW,
    ) -> None:
        if not robot_id or "/" in robot_id:
            raise ValueError("robot_id must be a non-empty name without slashes")
        self.robot_id = robot_id
        self._transport = transport
        self._registry = registry or TopicRegistry()
        self._clock = clock
        self._command_ttl = command_ttl
        self._max_clock_skew = max_clock_skew
        self._state = _State()
        self._published: OrderedDict[str, datetime] = OrderedDict()
        self._feedback: dict[str, list[FeedbackRecord]] = {}
        self._waiters: dict[str, asyncio.Future[FeedbackRecord]] = {}
        self._stats = BridgeStats()

    # ------------------------------------------------------------------ topics

    @property
    def topics(self) -> dict[str, str]:
        return {
            "odom": f"/{self.robot_id}/odom",
            "battery": f"/{self.robot_id}/battery_state",
            "feedback": f"/{self.robot_id}/task_feedback",
            "command": f"/{self.robot_id}/task_command",
        }

    @property
    def stats(self) -> BridgeStats:
        return self._stats

    async def start(self) -> None:
        handler: MessageHandler = self.handle_message
        for topic in (self.topics["odom"], self.topics["battery"], self.topics["feedback"]):
            await self._transport.subscribe(topic, handler)

    def handle_message(self, topic: str, payload: dict[str, Any]) -> None:
        self._stats.messages += 1
        try:
            decoded = self._registry.decode(topic, payload)
        except UnknownTopic:
            self._stats.unknown_topics += 1
            return
        except InvalidPayload:
            self._stats.invalid_payloads += 1
            return

        if decoded.robot_id != self.robot_id:
            self._stats.unknown_topics += 1
            return

        if decoded.kind == "odom":
            assert isinstance(decoded.payload, OdometryMessage)
            self._apply_odom(decoded.payload)
        elif decoded.kind == "battery":
            assert isinstance(decoded.payload, BatteryStateMessage)
            self._apply_battery(decoded.payload)
        else:
            assert isinstance(decoded.payload, TaskFeedbackMessage)
            self._apply_feedback(decoded.payload)

    def _is_stale(self, stamp: datetime) -> bool:
        """A packet far from the local clock is useless: either clock skew or a replay."""
        now = self._clock()
        return abs(stamp - now) > self._max_clock_skew

    def _apply_odom(self, message: OdometryMessage) -> None:
        stamp = message.header.stamp.to_datetime()
        if self._is_stale(stamp):
            self._stats.stale_messages += 1
            return
        self._state.stamp = stamp
        self._state.frame_id = message.header.frame_id
        self._state.x = round(message.pose.position.x, 3)
        self._state.y = round(message.pose.position.y, 3)
        self._state.yaw_rad = round(message.pose.orientation.yaw(), 4)
        self._state.speed_mps = round(message.twist.linear.x, 3)
        self._state.angular_speed_rps = round(message.twist.angular.z, 3)

    def _apply_battery(self, message: BatteryStateMessage) -> None:
        if not message.present:
            return
        stamp = message.header.stamp.to_datetime()
        if self._state.stamp is not None and stamp < self._state.stamp - self._max_clock_skew:
            self._stats.stale_messages += 1
            return
        self._state.battery_percent = round(message.percentage * 100.0, 1)

    def _apply_feedback(self, message: TaskFeedbackMessage) -> None:
        record = FeedbackRecord(
            command_id=message.command_id,
            task_id=message.task_id,
            state=message.state,
            progress=message.progress,
            detail=message.detail,
            error=message.error,
            received_at=self._clock(),
        )
        self._feedback.setdefault(message.command_id, []).append(record)
        self._stats.feedback_received += 1

        waiter = self._waiters.get(message.command_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(record)

    # ---------------------------------------------------------------- commands

    async def publish_command(self, command: TaskCommandPayload) -> PublishReceipt:
        """Publish once per `command_id`; duplicates are reported, not resent."""
        self._prune_published()
        topic = self.topics["command"]
        if command.command_id in self._published:
            self._stats.duplicate_commands += 1
            return PublishReceipt(command_id=command.command_id, topic=topic, duplicate=True)

        payload = command.model_dump(mode="json")
        try:
            await self._transport.publish(topic, payload)
        except Exception:
            self._stats.publish_failures += 1
            raise
        self._published[command.command_id] = self._clock()
        self._stats.commands_published += 1
        return PublishReceipt(command_id=command.command_id, topic=topic, duplicate=False)

    def _prune_published(self) -> None:
        threshold = self._clock() - self._command_ttl
        while self._published:
            command_id, published_at = next(iter(self._published.items()))
            if published_at >= threshold:
                break
            self._published.pop(command_id)

    # ------------------------------------------------------------------ state

    def telemetry(self) -> RobotTelemetry | None:
        if self._state.stamp is None:
            return None
        return RobotTelemetry(
            robot_id=self.robot_id,
            stamp=self._state.stamp,
            frame_id=self._state.frame_id,
            x=self._state.x,
            y=self._state.y,
            yaw_rad=self._state.yaw_rad,
            speed_mps=self._state.speed_mps,
            angular_speed_rps=self._state.angular_speed_rps,
            battery_percent=self._state.battery_percent,
        )

    def feedback_history(self, command_id: str) -> list[FeedbackRecord]:
        return list(self._feedback.get(command_id, []))

    async def wait_feedback(self, command_id: str, timeout_seconds: float = 5.0) -> FeedbackRecord:
        """Wait for the terminal feedback of a command, or fail loudly."""
        existing = self._terminal_feedback(command_id)
        if existing is not None:
            return existing

        loop = asyncio.get_running_loop()
        future: asyncio.Future[FeedbackRecord] = loop.create_future()
        self._waiters[command_id] = future
        try:
            record = await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise BridgeTimeout(command_id, timeout_seconds) from exc
        finally:
            self._waiters.pop(command_id, None)

        self._terminal_feedback(command_id)
        return record

    def _terminal_feedback(self, command_id: str) -> FeedbackRecord | None:
        for record in self._feedback.get(command_id, []):
            if record.state in {"succeeded", "failed"}:
                return record
        return None

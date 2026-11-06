"""Messages shaped like the real ROS2 interfaces, plus the internal normalized form.

The bridge never trusts a topic payload: ROS2 message definitions are strict
about units, frames and quaternion normalization, and a silent unit mix-up
(battery `0..1` vs `0..100`, radians vs degrees) is a classic integration bug.
Everything is validated on the way in.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class RosTime(BaseModel):
    """`builtin_interfaces/Time` as it appears in every ROS2 header."""

    model_config = ConfigDict(extra="forbid")

    sec: int = Field(ge=0)
    nanosec: int = Field(ge=0, lt=1_000_000_000)

    def to_datetime(self) -> datetime:
        return EPOCH + timedelta(seconds=self.sec, microseconds=self.nanosec // 1000)


class Header(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stamp: RosTime
    frame_id: str = Field(default="map", min_length=1, max_length=64)


class Vector3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @model_validator(mode="after")
    def _finite(self) -> Vector3:
        if not all(math.isfinite(value) for value in (self.x, self.y, self.z)):
            raise ValueError("vector components must be finite")
        return self


class Quaternion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @model_validator(mode="after")
    def _normalized(self) -> Quaternion:
        norm = math.sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)
        if abs(norm - 1.0) > 1e-2:
            raise ValueError(f"quaternion is not normalized (norm={norm:.4f})")
        return self

    def yaw(self) -> float:
        """Heading around Z in radians, for a planar robot."""
        siny_cosp = 2.0 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1.0 - 2.0 * (self.y**2 + self.z**2)
        return math.atan2(siny_cosp, cosy_cosp)


class Pose(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Vector3
    orientation: Quaternion = Field(default_factory=Quaternion)


class Twist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear: Vector3 = Field(default_factory=Vector3)
    angular: Vector3 = Field(default_factory=Vector3)


class OdometryMessage(BaseModel):
    """`nav_msgs/Odometry`, the subset the fleet actually publishes."""

    model_config = ConfigDict(extra="forbid")

    header: Header
    pose: Pose
    twist: Twist = Field(default_factory=Twist)


class BatteryStateMessage(BaseModel):
    """`sensor_msgs/BatteryState`: `percentage` is 0..1, not percent."""

    model_config = ConfigDict(extra="forbid")

    header: Header
    percentage: float = Field(ge=0.0, le=1.0)
    voltage: float = Field(default=0.0, ge=0.0)
    current: float = 0.0
    present: bool = True


class TaskFeedbackMessage(BaseModel):
    """Feedback published by the robot's mission node."""

    model_config = ConfigDict(extra="forbid")

    header: Header
    task_id: str = Field(min_length=1, max_length=64)
    command_id: str = Field(min_length=1, max_length=64)
    state: Literal["accepted", "running", "succeeded", "failed"]
    progress: float | None = Field(default=None, ge=0.0, le=100.0)
    detail: str | None = Field(default=None, max_length=512)
    error: str | None = Field(default=None, max_length=512)


class RobotTelemetry(BaseModel):
    """Normalized state the backend consumes (SI units, percent, radians)."""

    robot_id: str
    stamp: datetime
    frame_id: str
    x: float
    y: float
    yaw_rad: float
    speed_mps: float
    angular_speed_rps: float
    battery_percent: float


class TaskCommandPayload(BaseModel):
    """Command published to `/robotX/task_command`; `command_id` is the dedup key."""

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1, max_length=64)
    task_id: str = Field(min_length=1, max_length=64)
    task_type: str = Field(min_length=1, max_length=64)
    timeout_seconds: int = Field(ge=1, le=86_400)
    payload: dict[str, Any] = Field(default_factory=dict)
    issued_at: datetime

    @model_validator(mode="after")
    def _aware_issued_at(self) -> TaskCommandPayload:
        if self.issued_at.tzinfo is None:
            raise ValueError("issued_at must be timezone-aware")
        return self

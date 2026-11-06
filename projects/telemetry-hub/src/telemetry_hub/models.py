"""Validated telemetry contracts coming from the robot fleet.

MQTT payloads are untrusted: every field is validated here once, so the ingest
logic and the API never deal with half-parsed data.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RobotState(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    CHARGING = "charging"
    FAULT = "fault"
    OFFLINE = "offline"


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float = 0.0
    frame_id: str = "map"

    @field_validator("x", "y", "z")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("position must be finite")
        return value

    def distance_to(self, other: Position) -> float:
        return math.dist((self.x, self.y, self.z), (other.x, other.y, other.z))


class TelemetrySample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    robot_id: str = Field(min_length=1, max_length=64)
    seq: int = Field(ge=0, description="Per-robot monotonic sequence number")
    ts: datetime = Field(description="Device timestamp, must be timezone-aware")
    battery: float = Field(ge=0.0, le=100.0)
    state: RobotState = RobotState.IDLE
    position: Position | None = None
    metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("ts")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("ts must be timezone-aware")
        return value

    @field_validator("metrics")
    @classmethod
    def _finite_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        for key, item in value.items():
            if not math.isfinite(item):
                raise ValueError(f"metric {key} must be finite")
        return value


class RobotSnapshot(BaseModel):
    """Latest known state of one robot plus derived aggregates."""

    robot_id: str
    online: bool
    state: RobotState
    battery: float
    position: Position | None
    last_seq: int
    last_seen: datetime
    samples: int
    duplicates: int
    out_of_order: int
    distance_m: float
    avg_battery: float

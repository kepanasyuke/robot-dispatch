"""Topic registry: one place that maps ROS2 topic names to typed decoders.

Robot namespaces in ROS2 are convention, not schema: `/robot1/odom` and
`/robot1/odometry/filtered` may both exist. Instead of sprinkling string
comparisons across the bridge, every supported topic is declared once with a
pattern and a message type; unknown topics are counted and ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ValidationError

from ros2_bridge.contracts import (
    BatteryStateMessage,
    OdometryMessage,
    TaskFeedbackMessage,
)

TopicKind = Literal["odom", "battery", "feedback"]


class UnknownTopic(LookupError):
    def __init__(self, topic: str) -> None:
        self.topic = topic
        super().__init__(f"topic {topic} is not mapped by the bridge")


class InvalidPayload(ValueError):
    def __init__(self, topic: str, errors: int, detail: str) -> None:
        self.topic = topic
        self.errors = errors
        super().__init__(f"payload on {topic} is invalid: {detail}")


@lru_cache(maxsize=64)
def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Turn `/{robot}/odom` into a named-group regex, once per pattern."""
    escaped = re.escape(pattern)
    for match in re.finditer(r"\\\{(\w+)\\\}", escaped):
        escaped = escaped.replace(match.group(0), f"(?P<{match.group(1)}>[^/]+)")
    return re.compile(f"^{escaped}$")


@dataclass(frozen=True)
class TopicSpec:
    pattern: str
    kind: TopicKind
    message_type: type[BaseModel]

    def match(self, topic: str) -> dict[str, str] | None:
        found = compile_pattern(self.pattern).match(topic)
        return found.groupdict() if found else None


DEFAULT_SPECS: tuple[TopicSpec, ...] = (
    TopicSpec("/{robot}/odom", "odom", OdometryMessage),
    TopicSpec("/{robot}/battery_state", "battery", BatteryStateMessage),
    TopicSpec("/{robot}/task_feedback", "feedback", TaskFeedbackMessage),
)


@dataclass(frozen=True)
class DecodedMessage:
    kind: TopicKind
    robot_id: str
    topic: str
    payload: BaseModel


class TopicRegistry:
    def __init__(self, specs: tuple[TopicSpec, ...] = DEFAULT_SPECS) -> None:
        self._specs = specs

    @property
    def supported_topics(self) -> list[str]:
        return [spec.pattern for spec in self._specs]

    def resolve(self, topic: str) -> tuple[TopicSpec, str]:
        for spec in self._specs:
            groups = spec.match(topic)
            if groups is not None:
                return spec, groups["robot"]
        raise UnknownTopic(topic)

    def decode(self, topic: str, payload: dict) -> DecodedMessage:
        spec, robot_id = self.resolve(topic)
        try:
            message = spec.message_type.model_validate(payload)
        except ValidationError as exc:
            raise InvalidPayload(topic, exc.error_count(), str(exc.errors()[0]["msg"])) from exc
        return DecodedMessage(kind=spec.kind, robot_id=robot_id, topic=topic, payload=message)

from __future__ import annotations

import pytest
from ros2_bridge.contracts import OdometryMessage
from ros2_bridge.topics import InvalidPayload, TopicRegistry, UnknownTopic


def header(sec: int = 1000, frame_id: str = "map") -> dict:
    return {"stamp": {"sec": sec, "nanosec": 0}, "frame_id": frame_id}


def odom_payload(**overrides) -> dict:
    payload = {
        "header": header(),
        "pose": {
            "position": {"x": 1.5, "y": -2.0, "z": 0.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
        "twist": {"linear": {"x": 0.4, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.1}},
    }
    payload.update(overrides)
    return payload


def battery_payload(percentage: float = 0.87) -> dict:
    return {"header": header(), "percentage": percentage, "voltage": 24.1, "present": True}


class TestTopicRegistry:
    def test_resolves_robot_id_from_topic(self) -> None:
        registry = TopicRegistry()

        spec, robot_id = registry.resolve("/robot7/odom")

        assert robot_id == "robot7"
        assert spec.kind == "odom"

    def test_unknown_topic_is_rejected(self) -> None:
        registry = TopicRegistry()

        with pytest.raises(UnknownTopic):
            registry.resolve("/robot7/imu")

    def test_decode_returns_typed_message(self) -> None:
        registry = TopicRegistry()

        decoded = registry.decode("/robot7/odom", odom_payload())

        assert decoded.robot_id == "robot7"
        assert decoded.kind == "odom"
        assert isinstance(decoded.payload, OdometryMessage)
        assert decoded.payload.pose.position.x == 1.5

    def test_battery_percentage_follows_ros_spec(self) -> None:
        registry = TopicRegistry()

        decoded = registry.decode("/robot1/battery_state", battery_payload(0.42))
        assert decoded.kind == "battery"

        with pytest.raises(InvalidPayload):
            registry.decode("/robot1/battery_state", battery_payload(42.0))

    def test_unnormalized_quaternion_is_rejected(self) -> None:
        registry = TopicRegistry()
        broken = odom_payload()
        broken["pose"]["orientation"] = {"x": 0.9, "y": 0.9, "z": 0.9, "w": 0.9}

        with pytest.raises(InvalidPayload):
            registry.decode("/robot1/odom", broken)

    def test_supported_topics_are_documented(self) -> None:
        patterns = TopicRegistry().supported_topics

        assert "/{robot}/odom" in patterns
        assert "/{robot}/battery_state" in patterns
        assert "/{robot}/task_feedback" in patterns

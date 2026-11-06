from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

DESCRIPTOR: _descriptor.FileDescriptor

class Robot(_message.Message):
    __slots__ = ("id", "name", "status", "capabilities", "battery_percent", "last_seen_unix_ms")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    BATTERY_PERCENT_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    status: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    battery_percent: float
    last_seen_unix_ms: int
    def __init__(self, id: str | None = ..., name: str | None = ..., status: str | None = ..., capabilities: _Iterable[str] | None = ..., battery_percent: float | None = ..., last_seen_unix_ms: int | None = ...) -> None: ...

class GetRobotRequest(_message.Message):
    __slots__ = ("robot_id",)
    ROBOT_ID_FIELD_NUMBER: _ClassVar[int]
    robot_id: str
    def __init__(self, robot_id: str | None = ...) -> None: ...

class ListRobotsRequest(_message.Message):
    __slots__ = ("status", "limit")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    status: str
    limit: int
    def __init__(self, status: str | None = ..., limit: int | None = ...) -> None: ...

class ListRobotsResponse(_message.Message):
    __slots__ = ("robots",)
    ROBOTS_FIELD_NUMBER: _ClassVar[int]
    robots: _containers.RepeatedCompositeFieldContainer[Robot]
    def __init__(self, robots: _Iterable[Robot | _Mapping] | None = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("robot_id", "status", "battery_percent", "at_unix_ms")
    ROBOT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    BATTERY_PERCENT_FIELD_NUMBER: _ClassVar[int]
    AT_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    robot_id: str
    status: str
    battery_percent: float
    at_unix_ms: int
    def __init__(self, robot_id: str | None = ..., status: str | None = ..., battery_percent: float | None = ..., at_unix_ms: int | None = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("accepted", "server_time_unix_ms")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    SERVER_TIME_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    server_time_unix_ms: int
    def __init__(self, accepted: bool | None = ..., server_time_unix_ms: int | None = ...) -> None: ...

class DispatchTaskRequest(_message.Message):
    __slots__ = ("task_id", "command_id", "task_type", "robot_id", "timeout_seconds")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    ROBOT_ID_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    command_id: str
    task_type: str
    robot_id: str
    timeout_seconds: int
    def __init__(self, task_id: str | None = ..., command_id: str | None = ..., task_type: str | None = ..., robot_id: str | None = ..., timeout_seconds: int | None = ...) -> None: ...

class DispatchTaskResponse(_message.Message):
    __slots__ = ("command_id", "duplicate", "assigned_robot_id")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    DUPLICATE_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_ROBOT_ID_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    duplicate: bool
    assigned_robot_id: str
    def __init__(self, command_id: str | None = ..., duplicate: bool | None = ..., assigned_robot_id: str | None = ...) -> None: ...

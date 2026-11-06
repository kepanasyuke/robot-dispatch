from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from robot_dispatch.config import Settings
from robot_dispatch.db.models import Robot, Task
from robot_dispatch.domain.enums import RobotStatus
from robot_dispatch.repositories.memory import InMemoryUnitOfWorkFactory

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, moment: datetime = FIXED_NOW) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> datetime:
        self.moment = self.moment + timedelta(seconds=seconds)
        return self.moment


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        redis_url="",
        default_task_timeout_seconds=30,
        default_max_attempts=3,
        retry_base_delay_seconds=5,
        retry_max_delay_seconds=60,
        retry_jitter_ratio=0.0,
        robot_offline_after_seconds=30,
        dispatcher_batch_size=10,
        outbox_batch_size=50,
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def uow_factory() -> InMemoryUnitOfWorkFactory:
    return InMemoryUnitOfWorkFactory()


@pytest.fixture
def publisher():
    from robot_dispatch.messaging.publisher import RecordingPublisher

    return RecordingPublisher()


@pytest.fixture
async def robot(uow_factory, clock) -> Robot:
    robot = Robot.new(
        name="robot-1",
        namespace="/robot1",
        capabilities=["delivery"],
        status=RobotStatus.IDLE,
        last_seen_at=clock.moment,
    )
    async with uow_factory() as uow:
        await uow.robots.add(robot)
        await uow.commit()
    return robot


def make_task(**kwargs) -> Task:
    defaults = {
        "task_type": "delivery",
        "payload": {"target": "warehouse-a"},
        "priority": 100,
        "max_attempts": 3,
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return Task.new(**defaults)


@pytest.fixture
def task_factory():
    return make_task


def as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))

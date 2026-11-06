from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from telemetry_hub.ingest import IngestOutcome, TelemetryIngestor
from telemetry_hub.models import Position, RobotState, TelemetrySample

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
def ingestor(clock) -> TelemetryIngestor:
    return TelemetryIngestor(clock=clock)


def sample(
    seq: int,
    *,
    robot: str = "robot-1",
    battery: float = 90.0,
    state: RobotState = RobotState.IDLE,
    position: Position | None = None,
    ts: datetime | None = None,
    metrics: dict[str, float] | None = None,
) -> TelemetrySample:
    return TelemetrySample(
        robot_id=robot,
        seq=seq,
        ts=ts or BASE_TIME,
        battery=battery,
        state=state,
        position=position,
        metrics=metrics or {},
    )


def test_accepts_sample_and_builds_snapshot(ingestor) -> None:
    result = ingestor.apply(sample(1, position=Position(x=0, y=0)))

    assert result.outcome is IngestOutcome.ACCEPTED
    assert result.snapshot is not None
    assert result.snapshot.samples == 1
    assert result.snapshot.online is True
    assert result.snapshot.state is RobotState.IDLE


def test_duplicate_is_counted_not_applied(ingestor) -> None:
    ingestor.apply(sample(1, battery=90))
    result = ingestor.apply(sample(1, battery=10))

    assert result.outcome is IngestOutcome.DUPLICATE
    snapshot = ingestor.snapshot("robot-1")
    assert snapshot is not None
    assert snapshot.battery == 90
    assert snapshot.duplicates == 1
    assert snapshot.samples == 1


def test_late_sample_does_not_roll_state_back(ingestor) -> None:
    ingestor.apply(sample(5, battery=70, state=RobotState.BUSY))
    result = ingestor.apply(sample(3, battery=99, state=RobotState.CHARGING))

    assert result.outcome is IngestOutcome.OUT_OF_ORDER
    snapshot = ingestor.snapshot("robot-1")
    assert snapshot is not None
    assert snapshot.battery == 70
    assert snapshot.state is RobotState.BUSY
    assert snapshot.out_of_order == 1
    assert snapshot.samples == 1
    assert len(ingestor.history("robot-1")) == 2


def test_far_future_timestamp_is_rejected(ingestor, clock) -> None:
    future = clock.moment + timedelta(minutes=10)
    result = ingestor.apply(sample(1, ts=future))

    assert result.outcome is IngestOutcome.INVALID
    assert "future" in (result.detail or "")
    assert ingestor.snapshot("robot-1") is None


def test_aggregates_battery_average_and_distance(ingestor) -> None:
    ingestor.apply(sample(1, battery=100, position=Position(x=0, y=0)))
    ingestor.apply(sample(2, battery=80, position=Position(x=3, y=4)))
    ingestor.apply(sample(3, battery=60, position=Position(x=3, y=4)))

    snapshot = ingestor.snapshot("robot-1")
    assert snapshot is not None
    assert snapshot.distance_m == pytest.approx(5.0)
    assert snapshot.avg_battery == 80.0
    assert snapshot.samples == 3


def test_robot_goes_offline_after_window(ingestor, clock) -> None:
    ingestor.apply(sample(1))
    assert ingestor.snapshot("robot-1").online is True

    clock.advance(60)
    assert ingestor.snapshot("robot-1").online is False


def test_explicit_offline_state_is_never_online(ingestor) -> None:
    ingestor.apply(sample(1, state=RobotState.OFFLINE))
    assert ingestor.snapshot("robot-1").online is False


def test_queue_backpressure_keeps_newest(clock) -> None:
    ingestor = TelemetryIngestor(clock=clock, queue_maxsize=2)

    async def scenario() -> None:
        for seq in (1, 2, 3):
            await ingestor.offer(sample(seq))
        assert ingestor.queue_size == 2
        assert ingestor.stats()["dropped"] == 1
        processed = await ingestor.drain()
        assert processed == 2
        snapshot = ingestor.snapshot("robot-1")
        assert snapshot is not None
        assert snapshot.last_seq == 3

    asyncio.run(scenario())


async def test_run_loop_applies_queued_samples(ingestor) -> None:
    worker = asyncio.create_task(ingestor.run())
    try:
        await ingestor.offer(sample(1))
        await ingestor.offer(sample(2))
        for _ in range(20):
            if ingestor.queue_size == 0:
                break
            await asyncio.sleep(0.01)
    finally:
        ingestor.stop()
        await asyncio.wait_for(worker, timeout=2)

    snapshot = ingestor.snapshot("robot-1")
    assert snapshot is not None
    assert snapshot.samples == 2
    assert snapshot.last_seq == 2


def test_stats_breakdown(ingestor) -> None:
    ingestor.apply(sample(1, robot="robot-1", state=RobotState.IDLE))
    ingestor.apply(sample(1, robot="robot-1"))
    ingestor.apply(sample(1, robot="robot-2", state=RobotState.BUSY))

    stats = ingestor.stats()

    assert stats["robots"] == 2
    assert stats["accepted"] == 2
    assert stats["duplicates"] == 1
    assert stats["robots_busy"] == 1
    assert stats["queue_capacity"] == 1000

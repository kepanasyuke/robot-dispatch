"""Ingest policies: dedup, ordering, backpressure.

MQTT delivers at-least-once and without ordering guarantees per robot, so the
same sample can arrive twice, late, or after the broker restarts. The ingestor
makes the result deterministic:

* duplicate `(robot_id, seq)` -> counted and dropped;
* late sample (`seq` behind the newest one) -> recorded for history, keeps the
  current state intact: a delayed packet must not roll the state back;
* queue overflow -> the oldest sample is dropped and counted, so a burst of
  telemetry never blocks the consumer (keep-newest policy).
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from telemetry_hub.models import RobotSnapshot, TelemetrySample
from telemetry_hub.store import TelemetryLedger


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class IngestOutcome(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    INVALID = "invalid"


@dataclass(frozen=True)
class IngestResult:
    robot_id: str
    seq: int
    outcome: IngestOutcome
    detail: str | None = None
    snapshot: RobotSnapshot | None = None


class TelemetryIngestor:
    def __init__(
        self,
        *,
        ledger: TelemetryLedger | None = None,
        queue_maxsize: int = 1000,
        max_future_skew: timedelta = timedelta(seconds=30),
        clock=utcnow,
    ) -> None:
        self.ledger = ledger or TelemetryLedger()
        self._queue: asyncio.Queue[TelemetrySample] = asyncio.Queue(maxsize=queue_maxsize)
        self._queue_maxsize = queue_maxsize
        self._max_future_skew = max_future_skew
        self._clock = clock
        self._outcomes: Counter[str] = Counter()
        self._closed = asyncio.Event()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def apply(self, sample: TelemetrySample) -> IngestResult:
        """Synchronous policy application; also used by the worker loop."""
        now = self._clock()
        if sample.ts - now > self._max_future_skew:
            self._outcomes[IngestOutcome.INVALID.value] += 1
            return IngestResult(
                robot_id=sample.robot_id,
                seq=sample.seq,
                outcome=IngestOutcome.INVALID,
                detail="timestamp is too far in the future",
            )

        entry = self.ledger.entry(sample.robot_id)
        if sample.seq in entry.seen:
            self.ledger.track_duplicate(sample.robot_id)
            self._outcomes[IngestOutcome.DUPLICATE.value] += 1
            return IngestResult(
                robot_id=sample.robot_id, seq=sample.seq, outcome=IngestOutcome.DUPLICATE
            )

        if sample.seq < entry.last_seq:
            self.ledger.track_out_of_order(sample.robot_id)
            self.ledger.record_history(sample)
            self._outcomes[IngestOutcome.OUT_OF_ORDER.value] += 1
            return IngestResult(
                robot_id=sample.robot_id,
                seq=sample.seq,
                outcome=IngestOutcome.OUT_OF_ORDER,
                detail=f"last seq is {entry.last_seq}",
                snapshot=self.ledger.snapshot(sample.robot_id, now=now),
            )

        snapshot = self.ledger.apply(sample)
        self._outcomes[IngestOutcome.ACCEPTED.value] += 1
        return IngestResult(
            robot_id=sample.robot_id,
            seq=sample.seq,
            outcome=IngestOutcome.ACCEPTED,
            snapshot=snapshot,
        )

    async def offer(self, sample: TelemetrySample) -> None:
        """Queue a sample for the worker; drops the oldest one when saturated."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self.ledger.track_dropped()
                self._outcomes["dropped"] += 1
            except asyncio.QueueEmpty:  # pragma: no cover - racy but harmless
                pass
        await self._queue.put(sample)

    async def drain(self) -> int:
        """Apply everything currently queued; returns the number of samples."""
        processed = 0
        while not self._queue.empty():
            sample = self._queue.get_nowait()
            try:
                self.apply(sample)
                processed += 1
            finally:
                self._queue.task_done()
        return processed

    async def run(self) -> None:
        """Consumer loop: applies samples until `stop()` is called."""
        self._closed.clear()
        while not self._closed.is_set():
            try:
                sample = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            try:
                self.apply(sample)
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        self._closed.set()

    def snapshots(self) -> list[RobotSnapshot]:
        return self.ledger.snapshots(now=self._clock())

    def snapshot(self, robot_id: str) -> RobotSnapshot | None:
        if robot_id not in {item.robot_id for item in self.ledger.snapshots(now=self._clock())}:
            return None
        return self.ledger.snapshot(robot_id, now=self._clock())

    def history(self, robot_id: str, *, limit: int = 50) -> list[TelemetrySample]:
        return self.ledger.history(robot_id, limit=limit)

    def stats(self) -> dict[str, Any]:
        payload: dict[str, Any] = dict(self.ledger.stats())
        payload["queue_size"] = self.queue_size
        payload["queue_capacity"] = self._queue_maxsize
        payload["outcomes"] = dict(sorted(self._outcomes.items()))
        return payload

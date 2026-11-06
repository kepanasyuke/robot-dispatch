"""In-memory telemetry ledger.

The service is deliberately storage-agnostic: `TelemetryIngestor` owns the
policies (dedup, ordering, aggregates, backpressure), this module only keeps the
per-robot state. Swapping in Redis or TimescaleDB means reimplementing
`TelemetryLedger` without touching the policies.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from telemetry_hub.models import Position, RobotSnapshot, RobotState, TelemetrySample

DEFAULT_WINDOW = 20
DEFAULT_DEDUP_WINDOW = 512
DEFAULT_HISTORY = 100


@dataclass
class LedgerEntry:
    samples: int = 0
    duplicates: int = 0
    out_of_order: int = 0
    last_seq: int = -1
    last_seen: datetime | None = None
    state: RobotState = RobotState.OFFLINE
    battery: float = 0.0
    position: Position | None = None
    distance_m: float = 0.0
    battery_window: deque[float] = field(default_factory=lambda: deque(maxlen=DEFAULT_WINDOW))
    recent_seqs: deque[int] = field(default_factory=lambda: deque(maxlen=DEFAULT_DEDUP_WINDOW))
    seen: set[int] = field(default_factory=set)
    history: deque[TelemetrySample] = field(default_factory=lambda: deque(maxlen=DEFAULT_HISTORY))


class TelemetryLedger:
    def __init__(self, *, online_window: timedelta = timedelta(seconds=15)) -> None:
        self._entries: dict[str, LedgerEntry] = {}
        self._online_window = online_window
        self._accepted = 0
        self._duplicates = 0
        self._out_of_order = 0
        self._dropped = 0

    def entry(self, robot_id: str) -> LedgerEntry:
        entry = self._entries.get(robot_id)
        if entry is None:
            entry = LedgerEntry()
            self._entries[robot_id] = entry
        return entry

    def apply(self, sample: TelemetrySample) -> RobotSnapshot:
        """Apply an authoritative (ordered) sample and return the fresh snapshot."""
        entry = self.entry(sample.robot_id)
        if sample.position is not None and entry.position is not None:
            entry.distance_m += entry.position.distance_to(sample.position)

        entry.samples += 1
        entry.recent_seqs.append(sample.seq)
        entry.seen.add(sample.seq)
        self._prune(entry)
        entry.last_seq = max(entry.last_seq, sample.seq)
        entry.last_seen = sample.ts
        entry.state = sample.state
        entry.battery = sample.battery
        entry.battery_window.append(sample.battery)
        if sample.position is not None:
            entry.position = sample.position
        entry.history.append(sample)
        self._accepted += 1
        return self.snapshot(sample.robot_id, now=sample.ts)

    def record_history(self, sample: TelemetrySample) -> None:
        self.entry(sample.robot_id).history.append(sample)

    def track_duplicate(self, robot_id: str) -> None:
        self.entry(robot_id).duplicates += 1
        self._duplicates += 1

    def track_out_of_order(self, robot_id: str) -> None:
        self.entry(robot_id).out_of_order += 1
        self._out_of_order += 1

    def track_dropped(self, count: int = 1) -> None:
        self._dropped += count

    def snapshot(self, robot_id: str, *, now: datetime) -> RobotSnapshot:
        entry = self.entry(robot_id)
        last_seen = entry.last_seen
        online = bool(
            last_seen is not None
            and entry.state is not RobotState.OFFLINE
            and now - last_seen <= self._online_window
        )
        average = (
            sum(entry.battery_window) / len(entry.battery_window) if entry.battery_window else 0.0
        )
        return RobotSnapshot(
            robot_id=robot_id,
            online=online,
            state=entry.state,
            battery=round(entry.battery, 2),
            position=entry.position,
            last_seq=entry.last_seq,
            last_seen=last_seen or now,
            samples=entry.samples,
            duplicates=entry.duplicates,
            out_of_order=entry.out_of_order,
            distance_m=round(entry.distance_m, 2),
            avg_battery=round(average, 2),
        )

    def snapshots(self, *, now: datetime) -> list[RobotSnapshot]:
        return [self.snapshot(robot_id, now=now) for robot_id in sorted(self._entries)]

    def history(self, robot_id: str, *, limit: int = 50) -> list[TelemetrySample]:
        return list(self.entry(robot_id).history)[-limit:]

    def stats(self) -> dict[str, int]:
        states = Counter(entry.state.value for entry in self._entries.values())
        payload: dict[str, int] = {
            "robots": len(self._entries),
            "accepted": self._accepted,
            "duplicates": self._duplicates,
            "out_of_order": self._out_of_order,
            "dropped": self._dropped,
        }
        for state in RobotState:
            payload[f"robots_{state.value}"] = states.get(state.value, 0)
        return payload

    @staticmethod
    def _prune(entry: LedgerEntry) -> None:
        """Keep the dedup index bounded: forget sequences that left the window."""
        entry.seen &= set(entry.recent_seqs)

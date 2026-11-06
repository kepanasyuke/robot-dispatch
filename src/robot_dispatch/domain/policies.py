from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with a cap and optional jitter.

    Delays are used both for re-queueing tasks after a failed attempt and for
    re-delivering broken messages back to the consumer, so a dead robot or a
    crashed consumer never turns into a hot retry loop.
    """

    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 120.0
    jitter_ratio: float = 0.2

    def delay_seconds(self, attempt: int, *, rng: random.Random | None = None) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        raw = self.base_delay_seconds * (2 ** (attempt - 1))
        capped = min(raw, self.max_delay_seconds)
        if self.jitter_ratio <= 0:
            return capped
        generator = rng or random
        spread = capped * self.jitter_ratio
        return max(0.0, capped + generator.uniform(-spread, spread))


def should_retry(attempts_made: int, max_attempts: int) -> bool:
    return attempts_made < max_attempts

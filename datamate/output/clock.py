"""Time guard: the whole private test must finish within 6 hours including model loading; near the end the
pipeline stops computing and writes abstain for the questions left."""
from __future__ import annotations

import time


class TimeGuard:
    def __init__(self, budget_s: float, reserve_s: float = 0.0, start: float | None = None):
        """`start` is a time.monotonic() value; pass the process start so model loading counts too."""
        self.budget_s = budget_s
        self.reserve_s = reserve_s
        self.start = time.monotonic() if start is None else start

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def remaining(self) -> float:
        return self.budget_s - self.elapsed()

    def expired(self) -> bool:
        """True once less than `reserve_s` is left (the reserve covers writing the remaining abstains)."""
        return self.remaining() <= self.reserve_s

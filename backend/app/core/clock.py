"""The one place the application asks what time it is.

Every component that needs time takes a Clock. Tests hand it a fake one, so no assertion depends on
when the test happens to run (CLAUDE.md: "a test that reads the wall clock is a defect").
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Seconds on a clock that never goes backwards. For durations and cache ages only."""

    def now(self) -> datetime:
        """The current instant, timezone-aware, in UTC. For timestamps only."""


class SystemClock:
    def monotonic(self) -> float:
        # monotonic, not time.time(): an NTP correction moving the wall clock backwards would
        # otherwise produce negative request durations and a readiness cache that never expires.
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

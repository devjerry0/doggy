from __future__ import annotations

import time
from collections import deque
from typing import Callable

from doggy.core.runtime import RuntimeSettings
from doggy.decision.schedule import armed_state

_HOUR = 3600.0


class FireGate:
    """Decides whether a fire is allowed: master off switch, snooze, per-hour cap.

    Persistence is no longer its concern (that moved to ``Recorder``): the gate
    only answers ``allow``/``allow_escalation`` and remembers fire timestamps
    for the rolling rate limit via ``note_fire``.
    """

    def __init__(self, runtime: RuntimeSettings,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self._runtime = runtime
        # Wall-clock source for the arming schedule (the ``now`` args are the
        # monotonic clock used for snooze/rate limiting -- a different timeline).
        self._wall_clock = wall_clock
        self._fires: deque[float] = deque()
        self._snooze_until: float = 0.0

    def _prune(self, now: float) -> None:
        while self._fires and now - self._fires[0] >= _HOUR:
            self._fires.popleft()

    def fires_last_hour(self, now: float) -> int:
        self._prune(now)
        return len(self._fires)

    def snooze(self, seconds: float, now: float) -> None:
        self._snooze_until = now + seconds

    def cancel_snooze(self) -> None:
        self._snooze_until = 0.0

    def snooze_remaining(self, now: float) -> float:
        return max(0.0, self._snooze_until - now)

    def allow(self, now: float) -> bool:
        return self.allow_escalation(now)

    def allow_escalation(self, now: float) -> bool:
        """Follow-up strikes in one incident: no cooldown between them, but the
        master switch, snooze, and the hourly cap still apply."""
        cfg = self._runtime.get()
        if not cfg.safety_enabled:
            return False
        armed, _ = armed_state(cfg, self._wall_clock())
        if not armed:
            return False
        if now < self._snooze_until:
            return False
        return self.fires_last_hour(now) < cfg.max_fires_per_hour

    def note_fire(self, now: float) -> None:
        self._fires.append(now)

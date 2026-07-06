from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Callable

# `vcgencmd get_throttled` bitmask
# (https://www.raspberrypi.com/documentation/computers/os.html#get_throttled).
# The Pi 4B exposes no input-voltage/current ADC (that is Pi 5 only), so the
# meaningful power-health signal is the under-voltage bits of this mask:
_UNDERVOLT_NOW = 0x1  # bit 0  — under-voltage happening right now
_UNDERVOLT_SINCE_BOOT = 0x1_0000  # bit 16 — under-voltage has occurred since boot

# get_throttled changes slowly and needs a subprocess; polling it every detect
# loop would spawn vcgencmd ~1-2×/s. Re-read at most this often, serve cache between.
_MIN_READ_INTERVAL_SECONDS = 15.0
_VCGENCMD_TIMEOUT_SECONDS = 2.0


def _vcgencmd_throttled() -> int | None:
    """Return the raw `get_throttled` bitmask, or None if vcgencmd is unavailable."""
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=_VCGENCMD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # not a Pi / vcgencmd missing / hung
    # Output form: "throttled=0x0"
    _, _, value = out.stdout.strip().partition("=")
    try:
        return int(value, 16)
    except ValueError:
        return None


@dataclass(frozen=True)
class PowerStatus:
    """Parsed power-health from the throttle bitmask."""

    undervolt_now: bool  # supply is dipping below spec right now
    undervolt_since_boot: bool  # supply has dipped at least once since boot
    raw: int


class PowerMonitor:
    """Read the Pi's under-voltage flags via `vcgencmd get_throttled`, cached.

    Calling ``read`` every detect loop is cheap: the subprocess only actually
    runs once per ``min_interval``; intervening calls return the cached result.
    Returns None when vcgencmd is unavailable (e.g. a non-Pi dev machine).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 min_interval: float = _MIN_READ_INTERVAL_SECONDS,
                 reader: Callable[[], int | None] = _vcgencmd_throttled) -> None:
        self._clock = clock
        self._min_interval = min_interval
        self._reader = reader
        self._last_read: float | None = None
        self._cached: PowerStatus | None = None

    def read(self) -> PowerStatus | None:
        now = self._clock()
        if self._last_read is not None and now - self._last_read < self._min_interval:
            return self._cached
        self._last_read = now
        bits = self._reader()
        self._cached = None if bits is None else PowerStatus(
            undervolt_now=bool(bits & _UNDERVOLT_NOW),
            undervolt_since_boot=bool(bits & _UNDERVOLT_SINCE_BOOT),
            raw=bits,
        )
        return self._cached

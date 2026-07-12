from __future__ import annotations

import logging
import re
import subprocess

from fastapi import APIRouter

log = logging.getLogger("doggy")

# The master output level of the default PipeWire sink (the Bluetooth/USB
# speaker), controlled with wpctl. This is the hardware-side volume that scales
# EVERYTHING played out -- the deterrent, soothing loop, and push-to-talk -- on
# top of each sound's own per-stream gain. The session manager (wireplumber)
# remembers it across reboots, so there is nothing to persist here.
_SINK = "@DEFAULT_AUDIO_SINK@"


def _get() -> float | None:
    """Current sink volume 0..1, or None when wpctl/PipeWire is unavailable
    (e.g. a dev Mac) so the dashboard can hide the control gracefully."""
    try:
        done = subprocess.run(["wpctl", "get-volume", _SINK],
                              capture_output=True, text=True, timeout=3)
        if done.returncode != 0:
            return None
        m = re.search(r"Volume:\s*([0-9.]+)", done.stdout)  # "Volume: 1.00 [MUTED]"
        return float(m.group(1)) if m else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _set(volume: float) -> bool:
    level = f"{max(0.0, min(1.0, volume)):.3f}"
    try:
        done = subprocess.run(["wpctl", "set-volume", _SINK, level],
                              capture_output=True, timeout=3)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/speaker-volume")
    def get_speaker_volume() -> dict:
        return {"volume": _get()}

    @router.post("/api/speaker-volume")
    def set_speaker_volume(body: dict) -> dict:
        v = body.get("volume")
        if not isinstance(v, (int, float)):
            return {"ok": False}
        return {"ok": _set(float(v))}

    return router

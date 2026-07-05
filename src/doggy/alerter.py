from __future__ import annotations

import random
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol

from doggy.config import Settings
from doggy.state import RuntimeSettings

_CLIP_EXTS = {".wav", ".flac", ".ogg", ".mp3"}


def pick_clip(clips_dir: Path, rng: random.Random) -> Path | None:
    clips = sorted(p for p in Path(clips_dir).glob("*") if p.suffix.lower() in _CLIP_EXTS)
    if not clips:
        return None
    return rng.choice(clips)


class Alerter(Protocol):
    def alert(self) -> None: ...


class FakeAlerter:
    def __init__(self) -> None:
        self.calls = 0

    def alert(self) -> None:
        self.calls += 1


class SoundDeviceAlerter:
    """Plays a random clip on a background thread (fire-and-forget)."""

    def __init__(self, runtime: RuntimeSettings, rng: random.Random | None = None) -> None:
        self._runtime = runtime
        self._rng = rng or random.Random()

    def alert(self) -> None:
        cfg = self._runtime.get()
        clip = pick_clip(cfg.clips_dir, self._rng)
        if clip is None:
            return
        threading.Thread(target=self._play, args=(clip, cfg.max_volume), daemon=True).start()

    def _play(self, clip: Path, volume: float) -> None:
        import soundfile as sf
        import sounddevice as sd

        data, samplerate = sf.read(str(clip), dtype="float32")
        sd.play(data * max(0.0, min(1.0, volume)), samplerate)
        sd.wait()


class CommandAlerter:
    def __init__(self, runtime: RuntimeSettings, rng: random.Random | None = None) -> None:
        self._runtime = runtime
        self._rng = rng or random.Random()

    def alert(self) -> None:
        cfg = self._runtime.get()
        clip = pick_clip(cfg.clips_dir, self._rng)
        if clip is None:
            return
        cmd = "afplay" if sys.platform == "darwin" else "aplay"
        subprocess.Popen([cmd, str(clip)])  # non-blocking


def build_alerter(settings: Settings, runtime: RuntimeSettings) -> Alerter:
    if settings.alerter_backend == "log":
        return FakeAlerter()
    if settings.alerter_backend == "command":
        return CommandAlerter(runtime)
    return SoundDeviceAlerter(runtime)

from __future__ import annotations

import logging
from collections import deque
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger("doggy")


class ClipBuffer:
    """Rolling in-memory ring of ``(mono_ts, jpeg)`` frames.

    Holds only the most recent ``window_seconds`` of frames so a catch can be
    turned into a short clip WITHOUT any continuous SD writes -- nothing touches
    the card until a fire actually asks for a slice.
    """

    def __init__(self, window_seconds: float) -> None:
        self._window = float(window_seconds)
        self._frames: deque[tuple[float, bytes]] = deque()

    def push(self, mono_ts: float, jpeg: bytes) -> None:
        self._frames.append((mono_ts, jpeg))
        # Drop everything older than ``window_seconds`` behind the newest frame.
        cutoff = mono_ts - self._window
        while self._frames and self._frames[0][0] < cutoff:
            self._frames.popleft()

    def slice(self, start: float, end: float) -> list[bytes]:
        """JPEGs whose timestamp is in ``[start, end]``, oldest -> newest."""
        return [jpeg for ts, jpeg in self._frames if start <= ts <= end]


def encode_clip(frames: list[bytes], fps: int, out_path: Path) -> Path:
    """Encode JPEG ``frames`` into a short clip, returning the path written.

    Writes an MP4 via OpenCV's ``mp4v`` writer. If OpenCV cannot open the writer
    (no codec on the host) or it yields a missing/0-byte file, fall back to an
    animated WebP via Pillow and return that path instead.
    """
    out_path = Path(out_path)
    images = [
        cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR) for jpeg in frames
    ]
    images = [img for img in images if img is not None]
    if not images:
        raise ValueError("encode_clip: no decodable frames")

    h, w = images[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
    wrote = False
    if writer.isOpened():
        for img in images:
            writer.write(img)
        wrote = True
    writer.release()

    if wrote and out_path.is_file() and out_path.stat().st_size > 0:
        return out_path

    # Fallback: OpenCV lacks a usable MP4 encoder on this host. Emit an animated
    # WebP, which Pillow can always write, and drop any stray 0-byte MP4.
    log.warning("mp4 encode unavailable; writing animated webp fallback for %s", out_path.name)
    if out_path.exists():
        out_path.unlink()
    webp_path = out_path.with_suffix(".webp")
    pil_frames = [Image.open(BytesIO(jpeg)).convert("RGB") for jpeg in frames]
    pil_frames[0].save(
        webp_path,
        save_all=True,
        append_images=pil_frames[1:],
        loop=0,
        duration=int(1000 / fps),
    )
    return webp_path

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable

import cv2
import numpy as np

from doggy.alerter import Alerter
from doggy.camera import Camera
from doggy.config import Settings
from doggy.detection import Detection
from doggy.detector import Detector
from doggy.safety import SafetyGovernor
from doggy.state import FrameBuffer, RuntimeSettings, StatusStore
from doggy.trigger import TriggerLogic

log = logging.getLogger("doggy")

# Idle poll interval while the detect loop waits for the capture thread's
# first frame.
_IDLE_POLL_SECONDS = 0.01
# Detection-overlay styling (OpenCV uses BGR).
_BOX_COLOR = (0, 255, 0)
_BOX_THICKNESS = 2
_LABEL_FONT_SCALE = 0.5
_LABEL_THICKNESS = 1
_LABEL_Y_OFFSET = 6  # pixels above the box to place the label
# Decimal places for the status readouts the dashboard polls.
_CONFIDENCE_DECIMALS = 3
_FPS_DECIMALS = 1


def annotate(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    out = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d.box
        cv2.rectangle(out, (x1, y1), (x2, y2), _BOX_COLOR, _BOX_THICKNESS)
        cv2.putText(out, f"{d.label} {d.confidence:.2f}", (x1, max(0, y1 - _LABEL_Y_OFFSET)),
                    cv2.FONT_HERSHEY_SIMPLEX, _LABEL_FONT_SCALE, _BOX_COLOR, _LABEL_THICKNESS)
    return out


class Pipeline:
    def __init__(self, *, settings: Settings, detector: Detector, camera: Camera,
                 alerter: Alerter, runtime: RuntimeSettings, status: StatusStore,
                 raw_buffer: FrameBuffer, annotated_buffer: FrameBuffer,
                 safety: SafetyGovernor, clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None) -> None:
        self.settings = settings
        self.detector = detector
        self.camera = camera
        self.alerter = alerter
        self.runtime = runtime
        self.status = status
        self.raw_buffer = raw_buffer
        self.annotated_buffer = annotated_buffer
        self.safety = safety
        self.clock = clock
        self.trigger = TriggerLogic(runtime, rng=rng or random.Random())

    def run_once(self, frame: np.ndarray) -> bool:
        """Process a single frame: detect, annotate, trigger, maybe fire."""
        now = self.clock()
        detections = self.detector.detect(frame)
        self.annotated_buffer.set(annotate(frame, detections))
        top = max((d.confidence for d in detections), default=0.0)
        fired = self.trigger.update(detections, now)
        muted = not self.safety.allow_fire(now)
        if fired and not muted:
            self.alerter.alert()
            event = self.safety.record_fire(frame, top, now)
            self.status.add_event(event)
            self.status.update(last_fire_ts=event["ts"], last_fire_thumb=event["thumb"])
        self.status.update(state=self.trigger.state.value, confidence=round(top, _CONFIDENCE_DECIMALS),
                           fires_this_hour=self.safety.fires_last_hour(now), muted=muted)
        return fired and not muted

    def _capture_loop(self, stop: threading.Event) -> None:
        try:
            for frame in self.camera.frames():
                if stop.is_set():
                    return
                self.raw_buffer.set(frame)
        except Exception:
            log.exception("capture thread failed; signaling shutdown")
            stop.set()

    def run(self, stop: threading.Event) -> None:
        cap = threading.Thread(target=self._capture_loop, args=(stop,), daemon=True)
        cap.start()
        last = self.clock()
        while not stop.is_set():
            frame = self.raw_buffer.get()
            if frame is None:
                time.sleep(_IDLE_POLL_SECONDS)
                continue
            self.run_once(frame)
            now = self.clock()
            dt = now - last
            if dt > 0:
                self.status.update(fps=round(1.0 / dt, _FPS_DECIMALS))
            last = now
        self.camera.close()

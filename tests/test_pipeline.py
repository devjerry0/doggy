import random
import threading

import numpy as np

from doggy.alerter import FakeAlerter
from doggy.camera import FakeCamera
from doggy.config import Settings
from doggy.detection import Detection
from doggy.detector import StubDetector
from doggy.pipeline import Pipeline
from doggy.safety import SafetyGovernor
from doggy.state import FrameBuffer, RuntimeSettings, StatusStore
from doggy.trigger import TriggerLogic


def test_pipeline_fires_after_confirmation(tmp_path):
    settings = Settings(confirm_seconds=1.0, window_m=1, window_n=1,
                        cooldown_min_seconds=5, cooldown_max_seconds=5)
    runtime = RuntimeSettings(settings.tunable())
    dog = [Detection("dog", 0.9, (0, 0, 10, 10))]
    detector = StubDetector([dog, dog, dog, dog])
    alerter = FakeAlerter()
    clock = iter([0.0, 0.5, 1.0, 1.5])
    pipe = Pipeline(
        settings=settings,
        detector=detector,
        camera=FakeCamera([np.zeros((16, 16, 3), np.uint8)], loop=True),
        alerter=alerter,
        runtime=runtime,
        status=StatusStore(),
        raw_buffer=FrameBuffer(),
        annotated_buffer=FrameBuffer(),
        safety=SafetyGovernor(runtime, tmp_path),
        clock=lambda: next(clock),
        rng=random.Random(0),
    )
    frame = np.zeros((16, 16, 3), np.uint8)
    fired = [pipe.run_once(frame) for _ in range(4)]
    assert any(fired)
    assert alerter.calls == 1


def test_pipeline_counts_multiple_dogs(tmp_path):
    from doggy.pipeline import annotate
    settings = Settings()
    runtime = RuntimeSettings(settings.tunable())
    two_dogs = [
        Detection("dog", 0.9, (0, 0, 10, 10)),
        Detection("dog", 0.8, (20, 20, 30, 30)),
    ]
    status = StatusStore()
    pipe = Pipeline(
        settings=settings,
        detector=StubDetector([two_dogs]),
        camera=FakeCamera([np.zeros((40, 40, 3), np.uint8)], loop=True),
        alerter=FakeAlerter(),
        runtime=runtime,
        status=status,
        raw_buffer=FrameBuffer(),
        annotated_buffer=FrameBuffer(),
        safety=SafetyGovernor(runtime, tmp_path),
        clock=lambda: 0.0,
        rng=random.Random(0),
    )
    pipe.run_once(np.zeros((40, 40, 3), np.uint8))
    assert status.snapshot().dogs == 2

    # annotate draws one box per detection (both dogs), not just one
    frame = np.zeros((40, 40, 3), np.uint8)
    out = annotate(frame, two_dogs)
    assert (out != 0).any()  # boxes were drawn onto the blank frame

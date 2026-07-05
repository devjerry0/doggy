import random

from doggy.config import TunableSettings
from doggy.detection import Detection
from doggy.state import RuntimeSettings
from doggy.trigger import TriggerLogic, TriggerState

DOG = [Detection(label="dog", confidence=0.9, box=(0, 0, 10, 10))]
NONE: list[Detection] = []


def make(**over):
    base = dict(confirm_seconds=1.0, window_m=2, window_n=3,
               cooldown_min_seconds=10, cooldown_max_seconds=10, confidence=0.5)
    base.update(over)
    return TriggerLogic(RuntimeSettings(TunableSettings(**base)),
                        rng=random.Random(0))


def test_single_frame_does_not_fire():
    t = make()
    assert t.update(DOG, now=0.0) is False
    assert t.state is TriggerState.CONFIRMING


def test_fires_after_confirm_seconds():
    t = make()
    assert t.update(DOG, now=0.0) is False
    assert t.update(DOG, now=0.5) is False
    fired = t.update(DOG, now=1.0)  # 1.0s >= confirm_seconds
    assert fired is True
    assert t.state is TriggerState.COOLDOWN


def test_low_confidence_ignored():
    t = make(confidence=0.8)
    low = [Detection(label="dog", confidence=0.6, box=(0, 0, 1, 1))]
    assert t.update(low, now=0.0) is False
    assert t.state is TriggerState.IDLE


def test_lost_dog_resets_to_idle():
    t = make()
    t.update(DOG, now=0.0)
    t.update(NONE, now=0.1)
    t.update(NONE, now=0.2)  # window no longer M-of-N
    assert t.state is TriggerState.IDLE


def test_flicker_tolerated_by_m_of_n():
    t = make()  # window_m=2, window_n=3
    assert t.update(DOG, now=0.0) is False
    assert t.update(NONE, now=0.5) is False   # one dropped frame
    fired = t.update(DOG, now=1.0)            # 2 of last 3 had a dog, 1.0s elapsed
    assert fired is True


def test_cooldown_blocks_refire():
    t = make()
    t.update(DOG, now=0.0)
    assert t.update(DOG, now=1.0) is True     # fires, cooldown=10s
    assert t.update(DOG, now=2.0) is False    # still cooling down
    assert t.state is TriggerState.COOLDOWN


def test_refires_after_cooldown_with_fresh_confirm():
    t = make()
    t.update(DOG, now=0.0)
    assert t.update(DOG, now=1.0) is True
    assert t.update(DOG, now=12.0) is False   # cooldown expired -> fresh CONFIRMING
    assert t.update(DOG, now=13.0) is True     # confirmed again

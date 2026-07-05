import random

from doggy.alerter import FakeAlerter, pick_clip


def test_fake_alerter_counts_calls():
    a = FakeAlerter()
    a.alert()
    a.alert()
    assert a.calls == 2


def test_pick_clip_none_when_empty(tmp_path):
    assert pick_clip(tmp_path, random.Random(0)) is None


def test_pick_clip_is_deterministic_with_seed(tmp_path):
    for name in ["a.wav", "b.wav", "c.wav"]:
        (tmp_path / name).write_bytes(b"RIFF")
    chosen = pick_clip(tmp_path, random.Random(0))
    assert chosen.suffix == ".wav"
    assert pick_clip(tmp_path, random.Random(0)) == chosen  # same seed -> same pick

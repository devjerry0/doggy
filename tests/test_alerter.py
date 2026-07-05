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


def test_build_alerter_passes_audio_device():
    from doggy.alerter import SoundDeviceAlerter, build_alerter
    from doggy.config import Settings
    from doggy.state import RuntimeSettings

    s = Settings(alerter_backend="sounddevice", audio_device="USB Speaker")
    a = build_alerter(s, RuntimeSettings(s.tunable()))
    assert isinstance(a, SoundDeviceAlerter)
    assert a._device == "USB Speaker"


def test_sounddevice_play_passes_configured_device(monkeypatch, tmp_path):
    import sys
    import types

    import numpy as np

    from doggy.alerter import SoundDeviceAlerter
    from doggy.config import TunableSettings
    from doggy.state import RuntimeSettings

    calls = {}
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(
        play=lambda data, samplerate, device=None: calls.update(device=device),
        wait=lambda: None,
    ))
    monkeypatch.setitem(sys.modules, "soundfile", types.SimpleNamespace(
        read=lambda path, dtype: (np.zeros(4, dtype="float32"), 22050),
    ))
    a = SoundDeviceAlerter(RuntimeSettings(TunableSettings()), device="USB Speaker")
    a._play(tmp_path / "x.wav", 0.5)
    assert calls["device"] == "USB Speaker"

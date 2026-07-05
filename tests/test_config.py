import pytest
from pydantic import ValidationError

from doggy.config import Settings, TunableSettings, load_settings


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # avoid picking up a real .env
    s = load_settings()
    assert s.confidence == 0.55
    assert s.window_m == 4 and s.window_n == 6
    assert s.camera_index == 0
    assert s.web_host == "127.0.0.1"
    assert s.web_port == 8000


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DOGGY_CONFIDENCE", "0.7")
    monkeypatch.setenv("DOGGY_CAMERA_INDEX", "1")
    s = load_settings()
    assert s.confidence == 0.7
    assert s.camera_index == 1


def test_window_validation():
    with pytest.raises(ValidationError):
        TunableSettings(window_m=7, window_n=6)


def test_cooldown_validation():
    with pytest.raises(ValidationError):
        TunableSettings(cooldown_min_seconds=30, cooldown_max_seconds=10)


def test_confidence_range():
    with pytest.raises(ValidationError):
        TunableSettings(confidence=1.5)


def test_tunable_subset_extracted():
    s = Settings(confidence=0.6)
    t = s.tunable()
    assert isinstance(t, TunableSettings)
    assert t.confidence == 0.6
    assert not hasattr(t, "camera_index")

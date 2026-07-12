
from doggy.web.routers import speaker


class _Done:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_get_parses_wpctl_volume(monkeypatch):
    monkeypatch.setattr(speaker.subprocess, "run",
                        lambda *a, **k: _Done(0, "Volume: 0.75\n"))
    assert speaker._get() == 0.75


def test_get_handles_muted_suffix(monkeypatch):
    monkeypatch.setattr(speaker.subprocess, "run",
                        lambda *a, **k: _Done(0, "Volume: 1.00 [MUTED]\n"))
    assert speaker._get() == 1.0


def test_get_returns_none_when_wpctl_absent(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("wpctl")
    monkeypatch.setattr(speaker.subprocess, "run", boom)
    assert speaker._get() is None


def test_set_clamps_and_reports_success(monkeypatch):
    calls = {}

    def fake_run(cmd, **k):
        calls["cmd"] = cmd
        return _Done(0)

    monkeypatch.setattr(speaker.subprocess, "run", fake_run)
    assert speaker._set(1.5) is True                 # clamped, still succeeds
    assert calls["cmd"][:3] == ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@"]
    assert calls["cmd"][3] == "1.000"


def test_set_returns_false_on_error(monkeypatch):
    monkeypatch.setattr(speaker.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert speaker._set(0.5) is False

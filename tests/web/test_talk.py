import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from doggy.reaction.sound import FakeAlerter
from doggy.core.config import Settings
from doggy.events.store import EventStore
from doggy.decision.gate import FireGate
from doggy.core.runtime import RuntimeSettings
from doggy.core.status import FrameBuffer, StatusStore
from doggy.web import create_app
from doggy.web.routers import talk


def _client(tmp_path):
    settings = Settings(event_log_dir=tmp_path)
    runtime = RuntimeSettings(settings.tunable())
    store = EventStore(tmp_path, 100, 0)
    app = create_app(settings, runtime, FrameBuffer(), StatusStore(), FakeAlerter(),
                     store, FireGate(runtime))
    return TestClient(app)


class FakeProc:
    def __init__(self):
        self.stdin = self
        self.written = []

    def write(self, b):
        self.written.append(bytes(b))

    def flush(self):
        pass

    def close(self):
        pass

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass


def test_talk_pipes_frames_to_player(tmp_path, monkeypatch):
    proc = FakeProc()
    monkeypatch.setattr(talk, "_spawn_player", lambda: proc)
    c = _client(tmp_path)
    with c.websocket_connect("/ws/talk") as ws:
        ws.send_bytes(b"\x01\x02")
    assert proc.written == [b"\x01\x02"]


def test_second_talker_is_rejected(tmp_path, monkeypatch):
    # First talker holds the lock (blocked on receive); the second must be
    # accepted then closed with 1013 (try again later: someone is talking).
    monkeypatch.setattr(talk, "_spawn_player", lambda: None)
    c = _client(tmp_path)
    with c.websocket_connect("/ws/talk"):
        with c.websocket_connect("/ws/talk") as ws2:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws2.receive_bytes()
    assert exc.value.code == 1013


def test_index_has_talk_button(tmp_path):
    html = _client(tmp_path).get("/").text
    assert 'id="ptt"' in html
    assert "Hold to talk" in html
    assert "/ws/talk" in html


def test_missing_player_accepts_and_discards(tmp_path, monkeypatch):
    # No pw-cat on this host (Mac dev): the socket still opens and frames are
    # dropped without error, and the lock is released so a fresh talker works.
    monkeypatch.setattr(talk, "_spawn_player", lambda: None)
    c = _client(tmp_path)
    with c.websocket_connect("/ws/talk") as ws:
        ws.send_bytes(b"\x01\x02")
        ws.send_bytes(b"\x03\x04")
    with c.websocket_connect("/ws/talk") as ws:
        ws.send_bytes(b"\x05")

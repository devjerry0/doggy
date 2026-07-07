from datetime import datetime

from doggy.core.config import Settings, TunableSettings
from doggy.decision.gate import FireGate
from doggy.core.runtime import RuntimeSettings


def _gate(**over):
    base = dict(safety_enabled=True, max_fires_per_hour=2)
    base.update(over)
    rs = RuntimeSettings(TunableSettings(**base))
    return FireGate(rs)


# 2026-07-06 is a Monday; weeknights 21:00 -> 07:00.
_WINDOW_NIGHT = {"days": [0, 1, 2, 3, 4], "start": "21:00", "end": "07:00"}


def _scheduled_gate(wall_epoch):
    rs = RuntimeSettings(TunableSettings(
        safety_enabled=True, max_fires_per_hour=6,
        schedule_enabled=True, armed_windows=[_WINDOW_NIGHT]))
    return FireGate(rs, wall_clock=lambda: wall_epoch)


def test_allows_when_enabled_and_under_limit():
    g = _gate()
    assert g.allow(now=0.0) is True


def test_master_off_switch_blocks():
    g = _gate(safety_enabled=False)
    assert g.allow(now=0.0) is False


def test_rate_limit_blocks_after_max():
    g = _gate(max_fires_per_hour=2)
    g.note_fire(0.0)
    g.note_fire(10.0)
    assert g.allow(now=20.0) is False


def test_rate_limit_window_rolls_off():
    g = _gate(max_fires_per_hour=2)
    g.note_fire(0.0)
    g.note_fire(10.0)
    assert g.allow(now=3601.0) is True  # first fire aged out of the hour


def test_snooze_blocks_then_expires():
    g = _gate()
    g.snooze(60, now=100.0)
    assert g.allow(now=100.0) is False
    assert g.snooze_remaining(now=130.0) == 30.0
    assert g.allow(now=161.0) is True  # expired
    g.snooze(60, now=200.0)
    g.cancel_snooze()
    assert g.allow(now=200.0) is True


def test_escalation_master_off_switch_blocks():
    g = _gate(safety_enabled=False)
    assert g.allow_escalation(now=0.0) is False


def test_escalation_snooze_blocks_then_expires():
    g = _gate()
    g.snooze(60, now=100.0)
    assert g.allow_escalation(now=100.0) is False
    assert g.allow_escalation(now=161.0) is True  # expired


def test_escalation_rate_limit_blocks_after_max():
    g = _gate(max_fires_per_hour=2)
    g.note_fire(0.0)
    g.note_fire(10.0)
    assert g.allow_escalation(now=20.0) is False


def test_gate_allow_note_fire_preserves_hourly_cap():
    gate = FireGate(RuntimeSettings(Settings(max_fires_per_hour=2).tunable()))
    assert gate.allow(now=0.0)
    gate.note_fire(0.0)
    gate.note_fire(10.0)
    assert gate.allow(now=20.0) is False          # cap hit
    assert gate.allow(now=3610.0) is True         # oldest aged out


def test_schedule_off_duty_blocks_allow_and_escalation():
    outside = datetime(2026, 7, 6, 12, 0).timestamp()   # Monday noon: off duty
    g = _scheduled_gate(outside)
    assert g.allow(now=0.0) is False
    assert g.allow_escalation(now=0.0) is False


def test_schedule_on_duty_allows():
    inside = datetime(2026, 7, 6, 23, 0).timestamp()   # Monday night: armed
    g = _scheduled_gate(inside)
    assert g.allow(now=0.0) is True
    assert g.allow_escalation(now=0.0) is True


def test_schedule_disabled_ignores_wall_clock():
    # Default schedule_enabled=False -> the wall clock is irrelevant.
    rs = RuntimeSettings(TunableSettings(safety_enabled=True, max_fires_per_hour=6))
    g = FireGate(rs, wall_clock=lambda: 0.0)
    assert g.allow(now=0.0) is True
    assert g.allow_escalation(now=0.0) is True

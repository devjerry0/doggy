# Thermal Governor (adaptive detect interval) — Design

**Date:** 2026-07-05
**Status:** Approved

## Goal

The detector self-regulates its inference rate by CPU temperature: cruise at the
normal detect interval when cool, smoothly back off (longer interval → less load)
as it heats, so a bare-board Pi 4 in a hot spot **hovers at a safe temperature on
its own** instead of throttling — without ever stopping detection.

## Why proportional, not hysteresis

An on/off "slow above 80, fast below 70" design can get **stuck**: measured data
shows the board plateaus ~74°C even while backing off, so a 70°C exit threshold is
never reached and it'd stay slow forever. A **proportional** controller has no exit
threshold to miss — the interval scales continuously with temperature and
self-settles wherever heat-in = heat-out. Also stateless (no flap, no cooling flag).

## The control law

Effective interval as a function of CPU temp `t`:
- `t` unavailable (non-Pi / unreadable) OR `thermal_enabled=False` → `detect_interval_seconds` (governor inert).
- `t ≤ thermal_target_c` → `detect_interval_seconds` (full speed).
- `t ≥ thermal_max_c` → `thermal_cooldown_interval_seconds` (max backoff).
- between → linear ramp:
  `detect + (t-target)/(max-target) * (cooldown - detect)`.
- Guard: never faster than normal — return `max(detect_interval_seconds, ramped)`.

Example (defaults): 74°C→0.5s, 78°C→~1.0s, 82°C→1.5s (≈3s detection at the 2-of-3 trigger).

## Config (`TunableSettings` — env + live-tunable + `.env`)

- `thermal_enabled: bool = True`
- `thermal_target_c: float = 74.0` (below → normal speed)
- `thermal_max_c: float = 82.0` (at/above → max backoff)
- `thermal_cooldown_interval_seconds: float = 1.5` (the slow bound; keeps detection ≤ ~3s)
- Validator: `thermal_target_c ≤ thermal_max_c`.

## Components

### `ThermalGovernor` (new, `src/doggy/thermal.py`)
One responsibility: read CPU temp and map it to an interval. Stateless.
- `read_temp_c() -> float | None`: read `/sys/class/thermal/thermal_zone0/temp`
  (millidegrees ÷ 1000). Missing/unreadable → `None`. The path is a constructor
  arg (default the real one) so tests inject a temp file.
- `effective_interval(temp_c: float | None, cfg: TunableSettings) -> float`: the
  control law above.

### Pipeline (`pipeline.py`)
- `run` loop: `temp = gov.read_temp_c(); pacer.wait(gov.effective_interval(temp, cfg))`
  (replaces the fixed `detect_interval_seconds`). Publish `temp_c` and the
  `detect_interval_effective` to the status store so the UI can show them.
- `Pipeline.__init__` builds a `ThermalGovernor` (like it builds `ZoneFilter`/`Pacer`).

### Status + dashboard
- `Status` gains `temp_c: float | None = None` and `detect_interval_effective: float = 0.0`.
- Dashboard status line shows `🌡️ <temp>°C` and, when `detect_interval_effective >
  detect_interval_seconds`, a **"COOLING"** badge (so you see it easing off).

## Testing

- `read_temp_c`: injected temp file `"78123\n"` → `78.123`; missing file → `None`.
- `effective_interval`: `None`→normal; `≤target`→normal; `≥max`→cooldown;
  a midpoint temp → the interpolated value; the `max(detect, …)` guard when a
  user sets `cooldown < detect`.
- Config: `thermal_target_c ≤ thermal_max_c` validator.
- Pipeline: governor wired into the loop (unit-test `effective_interval` directly;
  the loop pacing is exercised as in the existing pattern).

## Non-goals (YAGNI)

Multi-zone thermal sensors, fan control (PWM), per-core temps, predictive control,
logging temp history. Just the adaptive interval + a readout.

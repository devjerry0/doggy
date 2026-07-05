# Detection Zone + Detection Interval — Design

**Date:** 2026-07-05
**Status:** Approved

## Goal

Let the user draw a **polygon zone** on the dashboard so that **only dogs inside
that zone trigger an alert** (dogs elsewhere are detected but ignored). Also add a
**detection interval** to cap inference rate for thermal relief without lowering
resolution.

## Context

The camera views a kitchen island at an angle, so the counter's footprint in the
image is an irregular quadrilateral — a rectangle can't fit it. The user wants to
trace the counter + its near approach as a polygon; a dog whose bounding box
overlaps that polygon should alert. The Pi 4 (bare board, hot location) thermal-
throttles under flat-out inference; a detection interval duty-cycles the CPU while
keeping `imgsz=640` (needed to spot a dog anywhere in a large scene).

## Config (`TunableSettings` — env-configurable, live-tunable, persisted to `.env`)

- `zone_enabled: bool = False` — when `False`, alert anywhere (today's behavior; no
  regression for existing deployments).
- `zone_points: list[tuple[float, float]] = []` — polygon vertices in **normalized
  [0,1]** coordinates (resolution-independent). Needs ≥3 points to form a zone.
- `detect_interval_seconds: float = 0.7` (`ge=0.0`) — minimum wall-clock time
  between inferences.

**`.env` persistence:** `_write_env` currently does `str(v)`, which emits a Python
repr (`[(0.1, 0.2)]`) that pydantic-settings can't re-parse. Fix: JSON-encode
non-scalar values (`json.dumps`) so `DOGGY_ZONE_POINTS=[[0.1,0.2],[0.3,0.4]]` round-
trips through env parsing.

## Components

### `ZoneFilter` (new, `src/doggy/zone.py`)
One clear responsibility: given normalized polygon points, decide which detections
are "in the zone" and expose the polygon for drawing.
- Caches a frame-sized `uint8` mask built with `cv2.fillPoly` from the points
  scaled to pixels; rebuilds only when the points or frame shape change.
- `in_zone(box, frame_shape) -> bool`: clamp the box to bounds, return
  `mask[y1:y2, x1:x2].any()` (true pixel overlap — robust for any polygon).
- `filter(detections, frame_shape) -> list[Detection]`: in-zone subset.
- When disabled / <3 points: `filter` returns detections unchanged (alert anywhere).

### `Pacer` (new, small helper — testable interval throttle)
- `Pacer(interval, clock, sleep)`; `.wait()` sleeps only the remainder since the
  last call. Injected clock + sleep so it unit-tests without real time.

### Pipeline (`pipeline.py`)
- `run_once`: run detector → `in_zone = zone.filter(all_detections, frame.shape)` →
  feed **`in_zone`** to `trigger.update` and report `dogs=len(in_zone)`. Pass both
  the full detections and the in-zone set to `annotate`.
- `run` loop: call `pacer.wait()` each iteration (interval from live runtime).
- `ZoneFilter` and `Pacer` read their params from `runtime.get()` live.

### Annotation (`pipeline.py::annotate`)
- Draw the zone polygon (scaled to frame): outline + semi-transparent fill
  (`cv2.fillPoly` on a copy + `addWeighted`).
- In-zone dogs → red box; out-of-zone dogs → grey box.

### Frontend (`static/index.html`)
- A `<canvas>` overlay positioned exactly over the MJPEG `<img>` (match rendered
  size via `getBoundingClientRect`).
- **Draw:** click drops a vertex (normalized via the img rect); polyline preview
  follows. **"Finish zone"** → `PATCH {zone_enabled:true, zone_points:[...]}`.
  **"Clear zone"** → `PATCH {zone_enabled:false, zone_points:[]}`.
- On poll, if not mid-draw, redraw the saved `zone_points` from `settings`.
- Add a `detect_interval_seconds` slider. Persist all via the existing **Save**.

## Data flow

frame → detector.detect → ZoneFilter.filter → TriggerLogic.update → alert; the
annotated buffer gets polygon + red/grey boxes; the run loop paces via Pacer.

## Testing

- `ZoneFilter`: point inside / outside / on edge; box fully in, fully out,
  straddling the boundary; disabled and <3-point cases pass through; mask rebuilds
  when points or frame shape change.
- `Pacer`: waits the remainder; no wait when interval already elapsed (injected
  clock/sleep).
- Pipeline: only in-zone detections reach the trigger and the `dogs` count.
- `_write_env` round-trips `zone_points` through JSON.

## Non-goals (YAGNI)

Multiple zones; freehand drawing; per-zone settings; non-rectangular box geometry
beyond pixel-mask overlap; editing individual vertices after finishing (Clear +
redraw instead).

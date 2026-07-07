from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from doggy.core.status import CONFIDENCE_DECIMALS

log = logging.getLogger("doggy")

EVENTS_FILE = "events.jsonl"

# A sound "deterred" the target when it left within this many seconds and took nothing.
DETERRED_WITHIN_S = 15.0
# Effective clear time scored when the target never left: the outcome watcher gives
# up at MAX_WATCH_SECONDS (60s), so a no-clear outcome counts as the full watch.
STAYED_CLEAR_S = 60.0


def _wearing_off(completed: list["EventRecord"]) -> bool:
    """True when a sound's recent clears run much slower than its early ones.

    Compares the average effective clear of the newer half of completed events
    against the older half (events arrive oldest -> newest). An odd count puts
    the extra event in the first half: the older, larger sample makes the
    steadier baseline for judging the newer events.
    """
    if len(completed) < 6:
        return False
    effective = [
        r.clear_seconds if r.clear_seconds is not None else STAYED_CLEAR_S
        for r in completed
    ]
    mid = (len(effective) + 1) // 2
    first = sum(effective[:mid]) / mid
    second = sum(effective[mid:]) / (len(effective) - mid)
    return second >= 1.5 * first


@dataclass
class EventRecord:
    """A single detected-dog reaction event, backed by a JPEG on the SD card."""

    id: str
    ts: float
    wall_time: float | None
    confidence: float
    latency_s: float | None
    thumb: str
    clip: str | None = None
    sound: str | None = None
    clear_seconds: float | None = None
    strikes: int = 1
    taken: list[str] = field(default_factory=list)
    outcome_at: float | None = None


class EventStore:
    """Disk-backed history of reaction events (JPEG + events.jsonl on the SD card).

    Source of truth for detected-dog events: each event writes a JPEG thumbnail
    and appends one JSON line. Old lines missing newer fields load with defaults.
    """

    def __init__(
        self,
        event_dir: Path,
        max_events: int = 500,
        max_age_days: int = 30,
        clip_retention: int = 10,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._dir = Path(event_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_events = max_events
        self._max_age_days = max_age_days
        self._clip_retention = clip_retention
        self._clock = clock
        # The pipeline thread writes (add/prune/attach_clip) while the web thread
        # reads and mutates (list/delete/clear/stats); every public method that
        # touches _records or the jsonl takes this lock. RLock so add -> prune
        # (and any other) nesting is safe.
        self._lock = threading.RLock()
        # Records kept in memory ordered oldest -> newest.
        self._backfilled = False
        self._records: list[EventRecord] = self._load()
        # Persist any wall_time backfilled from thumbnail mtimes (see _load).
        if self._backfilled:
            self._rewrite()

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def _jsonl(self) -> Path:
        return self._dir / EVENTS_FILE

    def _load(self) -> list[EventRecord]:
        path = self._jsonl
        if not path.is_file():
            return []
        records: list[EventRecord] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            # An abrupt power loss on the SD card can leave a torn/truncated final
            # line; a single bad line must not sink the whole history.
            try:
                obj = json.loads(line)
                thumb = obj["thumb"]
                wall_time = obj.get("wall_time")
                # Old events (pre-timestamp) have no wall_time, so they can't be
                # bucketed in stats or shown with a real date. Backfill from the
                # thumbnail's mtime -- the wall-clock moment the JPG was written,
                # i.e. when the catch happened -- so history stays usable.
                if wall_time is None:
                    thumb_path = self._dir / thumb
                    if thumb_path.is_file():
                        wall_time = thumb_path.stat().st_mtime
                        self._backfilled = True
                records.append(
                    EventRecord(
                        id=obj.get("id") or Path(thumb).stem,
                        ts=obj["ts"],
                        wall_time=wall_time,
                        confidence=obj["confidence"],
                        latency_s=obj.get("latency_s"),
                        thumb=thumb,
                        clip=obj.get("clip"),
                        sound=obj.get("sound"),
                        clear_seconds=obj.get("clear_seconds"),
                        strikes=int(obj.get("strikes") or 1),
                        taken=list(obj.get("taken") or []),
                        outcome_at=obj.get("outcome_at"),
                    )
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                log.warning("skipping malformed events.jsonl line: %r", line)
        return records

    def add(
        self,
        frame: np.ndarray,
        confidence: float,
        latency_s: float | None,
        wall_time: float | None,
        mono_ts: float,
    ) -> EventRecord:
        event_id = f"fire_{int(round((wall_time or mono_ts) * 1000))}"
        thumb = f"{event_id}.jpg"
        record = EventRecord(
            id=event_id,
            ts=mono_ts,
            wall_time=wall_time,
            confidence=round(float(confidence), CONFIDENCE_DECIMALS),
            latency_s=latency_s,
            thumb=thumb,
            clip=None,
        )
        cv2.imwrite(str(self._dir / thumb), frame)
        with self._lock:
            with self._jsonl.open("a") as fh:
                fh.write(json.dumps(asdict(record)) + "\n")
            self._records.append(record)
            self.prune()
        return record

    def list(self, limit: int | None = None) -> list[EventRecord]:
        with self._lock:
            recent_first = list(reversed(self._records))
        if limit is not None:
            return recent_first[:limit]
        return recent_first

    def delete(self, id: str) -> bool:
        with self._lock:
            for i, record in enumerate(self._records):
                if record.id == id:
                    self._delete_files(record)
                    del self._records[i]
                    self._rewrite()
                    return True
            return False

    def clear(self) -> None:
        with self._lock:
            for record in self._records:
                self._delete_files(record)
            self._records = []
            self._rewrite()

    def attach_clip(self, id: str, clip_name: str) -> None:
        with self._lock:
            for record in self._records:
                if record.id == id:
                    record.clip = clip_name
                    self._rewrite()
                    return

    def attach_sound(self, id: str, sound: str) -> None:
        with self._lock:
            for record in self._records:
                if record.id == id:
                    record.sound = sound
                    self._rewrite()
                    return

    def bump_strikes(self, id: str) -> None:
        with self._lock:
            for record in self._records:
                if record.id == id:
                    record.strikes += 1
                    self._rewrite()
                    return

    def attach_outcome(
        self,
        id: str,
        clear_seconds: float | None,
        taken: list[str],
        wall_time: float,
    ) -> None:
        with self._lock:
            for record in self._records:
                if record.id == id:
                    record.clear_seconds = clear_seconds
                    record.taken = list(taken)
                    record.outcome_at = wall_time
                    self._rewrite()
                    return

    def stats(self) -> dict:
        """Activity summary for the dashboard, bucketed by local wall-clock time."""
        today = datetime.fromtimestamp(self._clock()).date()
        # Last 7 calendar days, oldest -> newest, with today last.
        days = [today - timedelta(days=n) for n in range(6, -1, -1)]
        counts: dict = {day: 0 for day in days}
        hours: list[int] = []
        with self._lock:
            records = list(self._records)
        for record in records:
            if record.wall_time is None:
                continue
            dt = datetime.fromtimestamp(record.wall_time)
            hours.append(dt.hour)
            if dt.date() in counts:
                counts[dt.date()] += 1

        latencies = [r.latency_s for r in records if r.latency_s is not None]
        return {
            "today": counts[today],
            "this_week": sum(counts.values()),
            "per_day": [{"day": day.isoformat(), "count": counts[day]} for day in days],
            "busiest_hour": Counter(hours).most_common(1)[0][0] if hours else None,
            "avg_latency_s": sum(latencies) / len(latencies) if latencies else None,
        }

    def lab_stats(self) -> dict:
        """Per-sound deterrence effectiveness for the dashboard's lab card.

        A play is any event with that sound; it completes once the outcome
        watcher stamps ``outcome_at``. Deterred means the target left within
        DETERRED_WITHIN_S seconds without taking anything.
        """
        now = self._clock()
        with self._lock:
            records = list(self._records)

        # Same Pi-local calendar semantics as stats(): the last 7 local days.
        week = {datetime.fromtimestamp(now).date() - timedelta(days=n) for n in range(7)}
        thefts = sum(
            len(r.taken) for r in records
            if r.wall_time is not None and datetime.fromtimestamp(r.wall_time).date() in week
        )

        by_sound: dict[str, list[EventRecord]] = {}
        for r in records:  # _records is oldest -> newest, so groups stay in time order
            if r.sound:
                by_sound.setdefault(r.sound, []).append(r)

        sounds = []
        for sound, plays in by_sound.items():
            completed = [r for r in plays if r.outcome_at is not None]
            deterred = [
                r for r in completed
                if r.clear_seconds is not None
                and r.clear_seconds <= DETERRED_WITHIN_S
                and not r.taken
            ]
            clears = [r.clear_seconds for r in plays if r.clear_seconds is not None]
            sounds.append({
                "sound": sound,
                "plays": len(plays),
                "completed": len(completed),
                "deterred_rate": len(deterred) / len(completed) if completed else None,
                "avg_clear_s": sum(clears) / len(clears) if clears else None,
                "wearing_off": _wearing_off(completed),
            })
        sounds.sort(key=lambda s: s["plays"], reverse=True)
        return {"sounds": sounds, "thefts_this_week": thefts}

    def _delete_files(self, record: EventRecord) -> None:
        for name in (record.thumb, record.clip):
            if not name:
                continue
            path = self._dir / name
            if path.is_file():
                path.unlink()

    def prune(self) -> None:
        with self._lock:
            survivors = self._records
            dropped: list[EventRecord] = []

            if self._max_age_days > 0:
                now = self._clock()
                cutoff = self._max_age_days * 86400
                kept: list[EventRecord] = []
                for record in survivors:
                    if record.wall_time is not None and now - record.wall_time > cutoff:
                        dropped.append(record)
                    else:
                        kept.append(record)
                survivors = kept

            if self._max_events > 0 and len(survivors) > self._max_events:
                excess = len(survivors) - self._max_events
                dropped.extend(survivors[:excess])
                survivors = survivors[excess:]

            for record in dropped:
                self._delete_files(record)
            self._records = survivors

            # Clips are far heavier than thumbnails: keep only the newest N of them,
            # deleting older clip files (but keeping the event + its thumbnail).
            clips_changed = self._enforce_clip_retention()

            if dropped or clips_changed:
                self._rewrite()

    def _enforce_clip_retention(self) -> bool:
        if self._clip_retention <= 0:  # 0 = unlimited
            return False
        # _records is oldest -> newest, so with_clips is too.
        with_clips = [r for r in self._records if r.clip]
        excess = len(with_clips) - self._clip_retention
        if excess <= 0:
            return False
        for record in with_clips[:excess]:
            path = self._dir / record.clip
            if path.is_file():
                path.unlink()
            record.clip = None
        return True

    def _rewrite(self) -> None:
        with self._jsonl.open("w") as fh:
            for record in self._records:
                fh.write(json.dumps(asdict(record)) + "\n")

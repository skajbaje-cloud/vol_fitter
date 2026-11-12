"""Plain data holders for the snapshot scheduler (no logic)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")   # bit i of the days mask = DAY_NAMES[i]
WEEKDAYS_MASK = 0b0011111


@dataclass(frozen=True)
class ScheduleEntry:
    name_id: int
    name: str
    timezone: str | None
    days: int = WEEKDAYS_MASK
    enabled: bool = True
    active: bool = True
    times: tuple[time, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Firing:
    name_id: int
    name: str
    fire_utc: datetime          # naive UTC
    local_label: str            # e.g. "15:45 EST"


@dataclass(frozen=True)
class ScheduleRun:
    id: int
    name_id: int
    name: str
    scheduled_for_utc: datetime
    local_label: str | None
    status: str                 # queued | skipped_busy | missed | done | failed
    job_id: int | None
    reason: str | None

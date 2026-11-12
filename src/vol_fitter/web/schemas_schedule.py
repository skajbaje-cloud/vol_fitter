"""HTTP contract for the snapshot schedule and the scheduler's status."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from vol_fitter import config

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
Day = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleRunOut(BaseModel):
    name: str
    scheduled_for_utc: datetime
    local_label: str | None
    status: str
    job_id: int | None
    reason: str | None


class ScheduleRowOut(BaseModel):
    name: str
    display_name: str | None
    group_name: str | None
    active: bool
    timezone: str | None
    enabled: bool
    days: list[Day]
    times: list[str]                       # "HH:MM", sorted, local to `timezone`
    next_fire_utc: datetime | None
    next_fire_label: str | None
    last_run: ScheduleRunOut | None
    est_duration_sec: float | None         # latest snap duration, for the load estimate


class ScheduleOut(BaseModel):
    paused: bool
    names: list[ScheduleRowOut]


class ScheduleItemIn(BaseModel):
    name: str
    times: list[str] = Field(default_factory=list, max_length=config.SCHEDULE_MAX_SLOTS)
    days: list[Day] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    enabled: bool = True

    @field_validator("times")
    @classmethod
    def _times(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if not re.match(TIME_PATTERN, t)]
        if bad:
            raise ValueError(f"not a 24-hour HH:MM time: {', '.join(bad)}")
        if len(set(v)) != len(v):
            raise ValueError("the same time appears twice")
        return sorted(v)


class ScheduleSaveIn(BaseModel):
    items: list[ScheduleItemIn] = Field(min_length=1, max_length=500)


class UpcomingOut(BaseModel):
    name: str
    fire_utc: datetime
    local_label: str


class SchedulerStatusOut(BaseModel):
    enabled: bool                          # thread running in this server (VOL_FITTER_SCHEDULER)
    paused: bool
    last_tick_utc: datetime | None
    upcoming: list[UpcomingOut]
    recent_runs: list[ScheduleRunOut]


class PauseIn(BaseModel):
    paused: bool

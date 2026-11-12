"""Snapshot schedule: per-name local snap times, and the scheduler's status / pause switch."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.logging_setup import get_logger
from vol_fitter.scheduling.clock import days_to_mask, firings_between, mask_to_days, next_firing
from vol_fitter.scheduling.models import ScheduleEntry, ScheduleRun
from vol_fitter.scheduling.scheduler import is_paused, last_tick, set_paused, utcnow
from vol_fitter.web.deps import get_repo
from vol_fitter.web.schemas_schedule import (
    PauseIn, ScheduleOut, ScheduleRowOut, ScheduleRunOut, SchedulerStatusOut, ScheduleSaveIn, UpcomingOut,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["schedule"])

_UPCOMING = 10


def _run_out(r: ScheduleRun | None) -> ScheduleRunOut | None:
    if r is None:
        return None
    return ScheduleRunOut(name=r.name, scheduled_for_utc=r.scheduled_for_utc, local_label=r.local_label,
                          status=r.status, job_id=r.job_id, reason=r.reason)


def _fires(e: ScheduleEntry) -> bool:
    return e.enabled and e.active and bool(e.timezone)


@router.get("/schedule", response_model=ScheduleOut)
def get_schedule(repo: VolFitterRepository = Depends(get_repo)) -> ScheduleOut:
    names = {r.name: r for r in repo.list_names()}
    last, durations, now = repo.last_runs(), repo.last_snap_durations(), utcnow()
    rows = []
    for e in repo.list_schedules():
        rec = names[e.name]
        nxt = next_firing(e, now) if _fires(e) else None
        rows.append(ScheduleRowOut(
            name=e.name, display_name=rec.display_name, group_name=rec.group_name, active=e.active,
            timezone=e.timezone, enabled=e.enabled, days=mask_to_days(e.days),
            times=[f"{t:%H:%M}" for t in e.times],
            next_fire_utc=nxt.fire_utc if nxt else None, next_fire_label=nxt.local_label if nxt else None,
            last_run=_run_out(last.get(e.name_id)), est_duration_sec=durations.get(e.name_id),
        ))
    return ScheduleOut(paused=is_paused(repo), names=rows)


@router.put("/schedule", response_model=ScheduleOut)
def save_schedule(body: ScheduleSaveIn, repo: VolFitterRepository = Depends(get_repo)) -> ScheduleOut:
    """Replace the times/days/enabled of every listed name, in one transaction."""
    entries = {e.name: e for e in repo.list_schedules()}
    unknown = [i.name for i in body.items if i.name not in entries]
    if unknown:
        raise HTTPException(status_code=404, detail=f"Unknown underlying: {', '.join(unknown)}.")
    no_zone = [i.name for i in body.items if i.times and not entries[i.name].timezone]
    if no_zone:
        raise HTTPException(status_code=422, detail=f"Set a time zone first (Snapshot tab): {', '.join(no_zone)}.")
    repo.replace_schedules([
        (entries[i.name].name_id, [time.fromisoformat(t) for t in i.times], days_to_mask(i.days), i.enabled)
        for i in body.items
    ])
    return get_schedule(repo)


@router.get("/scheduler/status", response_model=SchedulerStatusOut)
def scheduler_status(request: Request, repo: VolFitterRepository = Depends(get_repo)) -> SchedulerStatusOut:
    now = utcnow()
    upcoming = sorted(
        (f for e in repo.list_schedules() if _fires(e) for f in firings_between(e, now, now + timedelta(days=4))),
        key=lambda f: f.fire_utc,
    )[:_UPCOMING]
    return SchedulerStatusOut(
        enabled=bool(getattr(request.app.state, "scheduler", None)), paused=is_paused(repo),
        last_tick_utc=last_tick(repo),
        upcoming=[UpcomingOut(name=f.name, fire_utc=f.fire_utc, local_label=f.local_label) for f in upcoming],
        recent_runs=[_run_out(r) for r in repo.recent_runs(20)],
    )


@router.post("/scheduler/pause", response_model=SchedulerStatusOut)
def pause_scheduler(body: PauseIn, request: Request, repo: VolFitterRepository = Depends(get_repo)) -> SchedulerStatusOut:
    set_paused(repo, body.paused)
    return scheduler_status(request, repo)

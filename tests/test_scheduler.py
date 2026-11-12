"""Scheduler against the `_test` database, with a fake job queue and a fake clock (no LSEG, no real time)."""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, time

import pytest

from vol_fitter.db.models import NameRecord
from vol_fitter.scheduling.models import WEEKDAYS_MASK
from vol_fitter.scheduling.scheduler import LAST_TICK_KEY, Scheduler, set_paused

NY = "America/New_York"
# 2031-03-04 is a Tuesday, before US daylight saving starts (Mar 9), so New York = UTC-5.
SLOT_A, SLOT_B, SLOT_C = time(9, 50), time(10, 50), time(11, 50)


def utc(h, m, day=4):
    return datetime(2031, 3, day, h, m)


@dataclass
class FakeJob:
    id: int
    name: str
    status: str = "queued"
    error: str | None = None


class FakeQueue:
    def __init__(self):
        self.jobs: dict[int, FakeJob] = {}
        self.busy: set[str] = set()
        self._ids = itertools.count(1)

    def has_live(self, kind, name):
        return name in self.busy

    def submit_snapshot(self, name, chain_ric=None, origin="manual"):
        job = FakeJob(next(self._ids), name)
        self.jobs[job.id] = job
        return job

    def get(self, job_id):
        return self.jobs.get(job_id)

    def names(self):
        return [j.name for j in self.jobs.values() if j.name.startswith("SCH.")]


@pytest.fixture(scope="module")
def sched_names(repo):
    ids = {}
    for name, tz, active in (("SCH.A", NY, True), ("SCH.B", NY, False), ("SCH.C", None, True), ("SCH.D", NY, True)):
        ids[name] = repo.get_or_create_name_id(NameRecord(name=name, chain_ric="0#SCH*.U", active=active, timezone=tz))
    slots = [SLOT_A, SLOT_B, SLOT_C]
    repo.replace_schedules([
        (ids["SCH.A"], slots, WEEKDAYS_MASK, True),
        (ids["SCH.B"], slots, WEEKDAYS_MASK, True),     # inactive name
        (ids["SCH.C"], slots, WEEKDAYS_MASK, True),     # no time zone
        (ids["SCH.D"], slots, WEEKDAYS_MASK, False),    # schedule switched off
    ])
    set_paused(repo, False)
    return ids


def _runs(repo, name):
    return [r for r in repo.recent_runs(500) if r.name == name]


def test_fires_once_and_reconciles(repo, sched_names):
    q = FakeQueue()
    s = Scheduler(lambda: repo, q, now_fn=lambda: datetime(2031, 3, 4, 14, 50, 20))   # 09:50 EST + 20s
    s.tick()
    s.tick()                                                      # same firing again: already claimed
    assert q.names() == ["SCH.A"]                                 # inactive, zone-less and disabled names skipped
    run = next(r for r in _runs(repo, "SCH.A") if r.scheduled_for_utc == utc(14, 50))
    assert run.status == "queued" and run.job_id is not None and run.local_label == "09:50 EST"

    q.jobs[run.job_id].status = "done"
    s.tick()
    run = next(r for r in _runs(repo, "SCH.A") if r.scheduled_for_utc == utc(14, 50))
    assert run.status == "done"


def test_busy_name_is_skipped(repo, sched_names):
    q = FakeQueue()
    q.busy.add("SCH.A")
    Scheduler(lambda: repo, q, now_fn=lambda: datetime(2031, 3, 4, 15, 51)).tick()
    assert q.names() == []
    run = next(r for r in _runs(repo, "SCH.A") if r.scheduled_for_utc == utc(15, 50))
    assert run.status == "skipped_busy"


def test_paused_scheduler_fires_nothing(repo, sched_names):
    q = FakeQueue()
    set_paused(repo, True)
    try:
        Scheduler(lambda: repo, q, now_fn=lambda: datetime(2031, 3, 4, 16, 51)).tick()
    finally:
        set_paused(repo, False)
    assert q.names() == []
    assert not [r for r in _runs(repo, "SCH.A") if r.scheduled_for_utc == utc(16, 50)]


def test_downtime_records_missed_and_catch_up_within_grace_fires(repo, sched_names):
    q = FakeQueue()
    repo.set_setting(LAST_TICK_KEY, "2031-03-05T08:00:00")
    s = Scheduler(lambda: repo, q, now_fn=lambda: datetime(2031, 3, 5, 15, 58))
    # Server back at 10:58 EST: 09:50 is past the 15-minute grace (missed); 10:50 is inside it (fires now).
    assert s.record_missed() >= 1
    s.tick()
    by_time = {r.scheduled_for_utc: r.status for r in _runs(repo, "SCH.A")}
    assert by_time[utc(14, 50, day=5)] == "missed"
    assert by_time[utc(15, 50, day=5)] == "queued"
    assert q.names() == ["SCH.A"]

"""Background thread that fires scheduled snapshots into the LSEG job queue.

Every tick it claims each due firing by inserting a schedule_runs row (unique on
name + instant, so a firing can never be queued twice, even across restarts),
then submits a snapshot job. Firings the server slept through by more than the
grace window are recorded as missed rather than run late.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from vol_fitter import config
from vol_fitter.logging_setup import get_logger
from vol_fitter.scheduling.clock import firings_between

logger = get_logger(__name__)

PAUSED_KEY = "scheduler_paused"
LAST_TICK_KEY = "scheduler_last_tick_utc"
_TS_FMT = "%Y-%m-%dT%H:%M:%S"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_paused(repo) -> bool:
    return repo.get_setting(PAUSED_KEY, "0") == "1"


def set_paused(repo, paused: bool) -> None:
    repo.set_setting(PAUSED_KEY, "1" if paused else "0")
    logger.info("scheduler %s", "paused" if paused else "resumed")


def last_tick(repo) -> datetime | None:
    raw = repo.get_setting(LAST_TICK_KEY)
    return datetime.strptime(raw, _TS_FMT) if raw else None


class Scheduler:
    def __init__(self, repo_factory: Callable, job_queue, now_fn: Callable[[], datetime] = utcnow,
                 tick_sec: float = config.SCHEDULE_TICK_SEC, grace_min: float = config.SCHEDULE_GRACE_MIN,
                 lookback_days: float = config.SCHEDULE_MISSED_LOOKBACK_DAYS):
        self.repo_factory = repo_factory
        self.jobs = job_queue
        self.now = now_fn
        self.tick_sec = tick_sec
        self.grace = timedelta(minutes=grace_min)
        self.lookback = timedelta(days=lookback_days)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="snap-scheduler", daemon=True)
        self._thread.start()
        logger.info("scheduler started (tick %ss, grace %s)", self.tick_sec, self.grace)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        self._guarded(self.record_missed)
        while not self._stop.is_set():
            self._guarded(self.tick)
            self._stop.wait(self.tick_sec)

    def _guarded(self, step: Callable[[], None]) -> None:
        try:
            step()
        except Exception:  # a DB hiccup must never kill the scheduler thread
            logger.exception("scheduler step %s failed", step.__name__)

    def record_missed(self) -> int:
        """After downtime: firings between the last tick and now - grace become 'missed' rows."""
        repo = self.repo_factory()
        now = self.now()
        since = max(last_tick(repo) or now, now - self.lookback)
        n = 0
        for entry in repo.list_schedules():
            if not (entry.enabled and entry.active):
                continue
            for f in firings_between(entry, since, now - self.grace):
                run_id = repo.insert_run(f.name_id, f.fire_utc, f.local_label, "missed",
                                         reason="server was not running at the scheduled time")
                n += run_id is not None
        if n:
            logger.warning("recorded %d missed scheduled snapshots", n)
        return n

    def tick(self) -> int:
        """Fire every due firing once; returns how many snapshot jobs were queued."""
        repo = self.repo_factory()
        now = self.now()
        self._reconcile(repo)
        queued = 0
        if not is_paused(repo):
            for entry in repo.list_schedules():
                if entry.enabled and entry.active:
                    for f in firings_between(entry, now - self.grace, now):
                        queued += self._fire(repo, f)
        repo.set_setting(LAST_TICK_KEY, now.strftime(_TS_FMT))
        return queued

    def _fire(self, repo, f) -> int:
        if self.jobs.has_live("snapshot", f.name):
            repo.insert_run(f.name_id, f.fire_utc, f.local_label, "skipped_busy",
                            reason="a snapshot of this name was already queued or running")
            return 0
        run_id = repo.insert_run(f.name_id, f.fire_utc, f.local_label, "queued")
        if run_id is None:
            return 0                                   # already claimed by an earlier tick
        job = self.jobs.submit_snapshot(f.name, origin="schedule")
        repo.update_run(run_id, job_id=job.id)
        logger.info("scheduled snapshot of %s (%s) queued as job %d", f.name, f.local_label, job.id)
        return 1

    def _reconcile(self, repo) -> None:
        """Copy finished jobs' outcomes onto their queued runs."""
        for run in repo.open_runs():
            job = self.jobs.get(run.job_id) if run.job_id is not None else None
            if job is None:
                if self.now() - run.scheduled_for_utc > self.grace:
                    repo.update_run(run.id, status="failed", reason="server restarted before the job reported back")
            elif job.status in ("done", "failed"):
                repo.update_run(run.id, status=job.status, reason=(job.error or "")[:255] or None)

"""In-process, serialized background job queues: one for everything that talks to LSEG, one for fits.

One worker thread, one job at a time: lseg.data keeps a single global session,
so a look-up running beside a snapshot could close the session under it.
Look-ups are quick and someone is waiting on them, so they jump the queue
(but never interrupt the running job). History lives in memory; restarting
the server clears it.
"""
from __future__ import annotations

import itertools
import queue
import threading
from datetime import datetime
from typing import Any, Callable

from vol_fitter.logging_setup import get_logger
from vol_fitter.web.models import JOB_KINDS, Job

logger = get_logger(__name__)

JobRunner = Callable[[dict], Any]   # payload -> result

_MAX_HISTORY = 200
_PRIORITY = {"lookup": 0}           # everything else 1, first come first served
_IDS = itertools.count(1)           # shared by every queue, so a job id is unique across them


class JobQueue:
    def __init__(self, runners: dict[str, JobRunner], worker_name: str = "lseg-worker"):
        unknown = set(runners) - set(JOB_KINDS)
        if unknown:
            raise ValueError(f"unknown job kinds: {sorted(unknown)}")
        self._runners = runners
        self._jobs: dict[int, Job] = {}
        self._lock = threading.Lock()
        self._queue: queue.PriorityQueue[tuple[int, int]] = queue.PriorityQueue()
        self._worker = threading.Thread(target=self._work, name=worker_name, daemon=True)
        self._worker.start()

    def submit(self, kind: str, name: str, payload: dict | None = None, origin: str = "manual") -> Job:
        if kind not in self._runners:
            raise ValueError(f"no runner for job kind '{kind}'")
        with self._lock:
            job = Job(id=next(_IDS), kind=kind, name=name, submitted_at=datetime.now(),
                      payload=payload or {}, origin=origin)
            self._jobs[job.id] = job
            self._trim()
        self._queue.put((_PRIORITY.get(kind, 1), job.id))
        logger.info("queued %s job %d for %s", kind, job.id, name)
        return job

    def submit_snapshot(self, name: str, chain_ric: str | None = None, origin: str = "manual") -> Job:
        return self.submit("snapshot", name, {"name": name, "chain_ric": chain_ric}, origin=origin)

    def has_live(self, kind: str, name: str) -> bool:
        """True if a job of this kind for this name is queued or running."""
        with self._lock:
            return any(j.kind == kind and j.name == name and j.status in ("queued", "running") for j in self._jobs.values())

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id, reverse=True)

    def stop(self) -> None:
        self._queue.put((-1, -1))

    def _trim(self) -> None:
        finished = [j for j in self._jobs.values() if j.status in ("done", "failed")]
        for j in sorted(finished, key=lambda j: j.id)[: max(0, len(self._jobs) - _MAX_HISTORY)]:
            del self._jobs[j.id]

    def _work(self) -> None:
        while True:
            _, job_id = self._queue.get()
            if job_id < 0:
                return
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job.status, job.started_at = "running", datetime.now()
            try:
                result = self._runners[job.kind](job.payload)
                with self._lock:
                    job.status, job.result = "done", result
            except Exception as exc:  # any failure is reported on the job, never kills the worker
                logger.exception("%s job %d for %s failed", job.kind, job.id, job.name)
                with self._lock:
                    job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
            finally:
                with self._lock:
                    job.finished_at = datetime.now()

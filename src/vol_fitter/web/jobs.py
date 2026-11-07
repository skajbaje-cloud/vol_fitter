"""In-process, serialized background job queue for snapshot runs.

One worker thread, one job at a time: concurrent LSEG sessions are untested,
and a universe snapshot is just a sequence of single-name runs anyway. Job
history lives in memory, so restarting the server clears it.
"""
from __future__ import annotations

import itertools
import queue
import threading
from datetime import datetime
from typing import Callable

from vol_fitter.logging_setup import get_logger
from vol_fitter.orchestration.models import SnapshotRunResult
from vol_fitter.web.models import Job

logger = get_logger(__name__)

SnapshotRunner = Callable[[str, str | None], SnapshotRunResult]

_MAX_HISTORY = 200


class JobQueue:
    def __init__(self, runner: SnapshotRunner):
        self._runner = runner
        self._jobs: dict[int, Job] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._worker = threading.Thread(target=self._work, name="snapshot-worker", daemon=True)
        self._worker.start()

    def submit_snapshot(self, name: str, chain_ric: str | None = None) -> Job:
        with self._lock:
            job = Job(id=next(self._ids), kind="snapshot", name=name, submitted_at=datetime.now(), chain_ric=chain_ric)
            self._jobs[job.id] = job
            self._trim()
        self._queue.put(job.id)
        logger.info("queued snapshot job %d for %s", job.id, name)
        return job

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id, reverse=True)

    def stop(self) -> None:
        self._queue.put(None)

    def _trim(self) -> None:
        finished = [j for j in self._jobs.values() if j.status in ("done", "failed")]
        for j in sorted(finished, key=lambda j: j.id)[: max(0, len(self._jobs) - _MAX_HISTORY)]:
            del self._jobs[j.id]

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job.status, job.started_at = "running", datetime.now()
            try:
                result = self._runner(job.name, job.chain_ric)
                with self._lock:
                    job.status, job.result = "done", result
            except Exception as exc:  # any failure in a run is reported on the job, never kills the worker
                logger.exception("snapshot job %d for %s failed", job.id, job.name)
                with self._lock:
                    job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
            finally:
                with self._lock:
                    job.finished_at = datetime.now()

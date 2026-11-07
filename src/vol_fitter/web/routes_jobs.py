"""Kick off snapshot runs and poll their progress."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.web.deps import get_job_queue, get_repo
from vol_fitter.web.jobs import JobQueue
from vol_fitter.web.models import Job
from vol_fitter.web.schemas import JobOut, SnapshotRunRequest

router = APIRouter(prefix="/api", tags=["jobs"])


def _to_out(job: Job) -> JobOut:
    r = job.result
    return JobOut(
        id=job.id, kind=job.kind, name=job.name, status=job.status,
        submitted_at=job.submitted_at, started_at=job.started_at, finished_at=job.finished_at, error=job.error,
        snapshot_ts=r.snapshot_ts if r else None, spot=r.spot if r else None,
        window_vol=r.window_vol if r else None, window_size=r.window_size if r else None,
        n_quotes=r.n_quotes if r else None, n_maturities=r.n_maturities if r else None,
        duration_sec=r.duration_sec if r else None,
    )


@router.post("/snapshots/run", response_model=list[JobOut], status_code=202)
def run_snapshots(
    req: SnapshotRunRequest,
    repo: VolFitterRepository = Depends(get_repo),
    jobs: JobQueue = Depends(get_job_queue),
) -> list[JobOut]:
    if req.scope == "universe":
        names = [r.name for r in repo.list_names(active_only=True)]
        if not names:
            raise HTTPException(status_code=400, detail="No active names to snapshot.")
        return [_to_out(jobs.submit_snapshot(n)) for n in names]

    if not req.underlying:
        raise HTTPException(status_code=400, detail="Pick an underlying, or choose the universe scope.")
    if repo.get_name(req.underlying) is None and not req.chain_ric:
        raise HTTPException(status_code=400, detail=f"'{req.underlying}' isn't registered yet; supply its chain RIC.")
    return [_to_out(jobs.submit_snapshot(req.underlying, req.chain_ric))]


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(jobs: JobQueue = Depends(get_job_queue)) -> list[JobOut]:
    return [_to_out(j) for j in jobs.list_jobs()]

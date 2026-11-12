"""Kick off snapshot runs and poll every background job (snapshots, look-ups, chain checks, fits)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.web.deps import get_all_queues, get_job_queue, get_repo
from vol_fitter.web.job_out import job_out
from vol_fitter.web.jobs import JobQueue
from vol_fitter.web.schemas import JobOut, SnapshotRunRequest

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/snapshots/run", response_model=list[JobOut], status_code=202)
def run_snapshots(
    req: SnapshotRunRequest,
    repo: VolFitterRepository = Depends(get_repo),
    jobs: JobQueue = Depends(get_job_queue),
) -> list[JobOut]:
    known = {r.name for r in repo.list_names()}
    missing = [n for n in dict.fromkeys(req.names) if n not in known]
    if missing:
        raise HTTPException(status_code=400, detail=f"Register these names first: {', '.join(missing)}.")
    return [job_out(jobs.submit_snapshot(n)) for n in dict.fromkeys(req.names)]


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(repo: VolFitterRepository = Depends(get_repo), queues: list[JobQueue] = Depends(get_all_queues)) -> list[JobOut]:
    registered = {r.name for r in repo.list_names()}
    every = sorted((j for q in queues for j in q.list_jobs()), key=lambda j: j.id, reverse=True)
    return [job_out(j, registered) for j in every]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, repo: VolFitterRepository = Depends(get_repo),
            queues: list[JobQueue] = Depends(get_all_queues)) -> JobOut:
    job = next((j for q in queues if (j := q.get(job_id)) is not None), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id} (history clears when the server restarts).")
    return job_out(job, {r.name for r in repo.list_names()})

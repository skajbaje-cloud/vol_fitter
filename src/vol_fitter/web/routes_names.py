"""Names: browse what's in the database, add and edit names, and look RICs up in LSEG.

Look-ups and chain checks touch LSEG, so they run as background jobs (poll
/api/jobs/{id}); registering and editing are plain database writes.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException

from vol_fitter.db.models import NameRecord
from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.web.deps import get_job_queue, get_repo, require_name
from vol_fitter.web.job_out import job_out
from vol_fitter.web.jobs import JobQueue
from vol_fitter.web.schemas import JobOut
from vol_fitter.web.schemas_names import RIC_PATTERN, ChainCheckRequest, LookupRequest, NameIn, NameOut, NamePatch

router = APIRouter(prefix="/api/names", tags=["names"])


def _out(r: NameRecord, last: dict[int, datetime]) -> NameOut:
    return NameOut(
        name_id=r.name_id, name=r.name, chain_ric=r.chain_ric, display_name=r.display_name, active=r.active,
        group_name=r.group_name, expiry_filter=r.expiry_filter, timezone=r.timezone,
        last_snapshot_ts=last.get(r.name_id),
    )


@router.get("", response_model=list[NameOut])
def list_names(repo: VolFitterRepository = Depends(get_repo)) -> list[NameOut]:
    last = repo.last_snapshot_times()
    return [_out(r, last) for r in repo.list_names()]


@router.post("", response_model=list[NameOut], status_code=201)
def register_names(body: list[NameIn], repo: VolFitterRepository = Depends(get_repo)) -> list[NameOut]:
    """Add new names. Existing names are rejected rather than overwritten (edit those with PATCH)."""
    taken = [n.name for n in body if repo.get_name(n.name) is not None]
    if taken:
        raise HTTPException(status_code=409, detail=f"Already registered: {', '.join(taken)}.")
    for n in body:
        repo.get_or_create_name_id(NameRecord(**n.model_dump()))
    last = repo.last_snapshot_times()
    return [_out(repo.get_name(n.name), last) for n in body]


@router.patch("/{name}", response_model=NameOut)
def edit_name(name: str, patch: NamePatch, repo: VolFitterRepository = Depends(get_repo)) -> NameOut:
    require_name(repo, name)
    record = repo.update_name(name, **patch.model_dump(exclude_unset=True))
    return _out(record, repo.last_snapshot_times())


@router.post("/lookup", response_model=JobOut, status_code=202)
def lookup(req: LookupRequest, jobs: JobQueue = Depends(get_job_queue)) -> JobOut:
    rics = list(dict.fromkeys(r.strip() for r in req.rics if r.strip()))
    bad = [r for r in rics if not re.fullmatch(RIC_PATTERN, r)]
    if bad or not rics:
        raise HTTPException(status_code=400, detail=f"Not a valid RIC: {', '.join(bad) or '(none given)'}.")
    return job_out(jobs.submit("lookup", ", ".join(rics), {"rics": rics}))


@router.post("/check", response_model=JobOut, status_code=202)
def check_chain(req: ChainCheckRequest, jobs: JobQueue = Depends(get_job_queue)) -> JobOut:
    return job_out(jobs.submit("check", req.name, {"name": req.name, "chain_ric": req.chain_ric}))


@router.get("/{name}/snapshots", response_model=list[datetime])
def list_snapshots(name: str, repo: VolFitterRepository = Depends(get_repo)) -> list[datetime]:
    record = require_name(repo, name)
    return repo.list_snapshot_timestamps(record.name_id)


@router.get("/{name}/snapshots/{snapshot_ts}/maturities", response_model=list[date])
def list_maturities(name: str, snapshot_ts: datetime, repo: VolFitterRepository = Depends(get_repo)) -> list[date]:
    record = require_name(repo, name)
    return repo.list_maturities(record.name_id, snapshot_ts)

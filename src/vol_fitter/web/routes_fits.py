"""Smile fits from the console: queue fit jobs, and read fit coverage and per-expiry results."""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from vol_fitter.db.repository import VolFitterRepository
from vol_fitter.logging_setup import get_logger
from vol_fitter.web.deps import get_fit_queue, get_repo, require_name
from vol_fitter.web.job_out import job_out
from vol_fitter.web.jobs import JobQueue
from vol_fitter.web.schemas import JobOut
from vol_fitter.web.schemas_fits import ExpiryFitOut, FitCoverageOut, FitRunRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/api/fits", tags=["fits"])


def _clean(value):
    """pandas NaN / NaT / numpy scalars -> plain JSON-able values."""
    if value is None or value is pd.NaT or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value.item() if hasattr(value, "item") else value


def _records(df: pd.DataFrame, fields) -> list[dict]:
    return [{k: _clean(r.get(k)) for k in fields} for r in df.to_dict("records")]


@router.post("/run", response_model=list[JobOut], status_code=202)
def run_fits(req: FitRunRequest, repo: VolFitterRepository = Depends(get_repo),
             fits: JobQueue = Depends(get_fit_queue)) -> list[JobOut]:
    known = {r.name for r in repo.list_names()}
    missing = [n for n in dict.fromkeys(req.names) if n not in known]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown underlying: {', '.join(missing)}.")
    ts = req.snapshot_ts.isoformat() if req.snapshot_ts else None
    return [job_out(fits.submit("fit", n, {"name": n, "mode": req.mode, "snapshot_ts": ts, "anchor": req.anchor}))
            for n in dict.fromkeys(req.names)]


@router.get("/coverage", response_model=list[FitCoverageOut])
def coverage(repo: VolFitterRepository = Depends(get_repo)) -> list[FitCoverageOut]:
    """Every stored snapshot with how many of its expiries are fitted, and how well."""
    return [FitCoverageOut(**r) for r in _records(repo.fit_coverage(), FitCoverageOut.model_fields)]


@router.get("/{name}/{snapshot_ts}", response_model=list[ExpiryFitOut])
def expiry_fits(name: str, snapshot_ts: datetime, repo: VolFitterRepository = Depends(get_repo)) -> list[ExpiryFitOut]:
    record = require_name(repo, name)
    df = repo.fetch_maturity_params(record.name_id, snapshot_ts)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No snapshot of {name} at {snapshot_ts}.")
    return [ExpiryFitOut(**r) for r in _records(df.sort_values("expiry_date"), ExpiryFitOut.model_fields)]

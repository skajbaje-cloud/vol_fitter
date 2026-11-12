"""Job -> JobOut, flattening whichever result the job's kind produced."""
from __future__ import annotations

from dataclasses import asdict

from vol_fitter.scheduling.tz_guess import guess_timezone
from vol_fitter.web.models import Job
from vol_fitter.orchestration.models import FitRunResult
from vol_fitter.web.schemas import ChainCheckOut, JobOut, NameLookupOut
from vol_fitter.web.schemas_fits import FitSnapshotSummaryOut


def job_out(job: Job, registered: set[str] | None = None) -> JobOut:
    out = JobOut(
        id=job.id, kind=job.kind, name=job.name, status=job.status, submitted_at=job.submitted_at,
        started_at=job.started_at, finished_at=job.finished_at, error=job.error, origin=job.origin,
    )
    r = job.result
    if r is None:
        return out
    if job.kind == "snapshot":
        out.snapshot_ts, out.spot, out.window_vol = r.snapshot_ts, r.spot, r.window_vol
        out.window_size, out.n_quotes, out.n_maturities, out.duration_sec = r.window_size, r.n_quotes, r.n_maturities, r.duration_sec
    elif job.kind == "lookup":
        out.lookup = [NameLookupOut(**asdict(x), registered=x.ric in (registered or set()),
                                  timezone_guess=guess_timezone(x.ric)) for x in r]
    elif job.kind == "check":
        out.check = ChainCheckOut(**asdict(r))
        out.duration_sec = r.duration_sec
    elif job.kind == "fit":
        out.fit = [_fit_summary(x) for x in r]
        out.duration_sec = sum(x.duration_sec for x in r)
    return out


def _fit_summary(r: FitRunResult) -> FitSnapshotSummaryOut:
    inside = [e.pct_inside for e in r.expiries]
    return FitSnapshotSummaryOut(
        snapshot_ts=r.snapshot_ts, n_expiries=len(r.expiries), n_ok=sum(e.status == "ok" for e in r.expiries),
        mean_pct_inside=sum(inside) / len(inside) if inside else None, min_pct_inside=min(inside) if inside else None,
        n_outliers=sum(e.n_outliers for e in r.expiries), n_model_miss=sum(e.n_model_miss for e in r.expiries),
        duration_sec=r.duration_sec,
    )
